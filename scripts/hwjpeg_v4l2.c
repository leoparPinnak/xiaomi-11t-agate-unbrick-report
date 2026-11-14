#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>

struct mtk_ion_allocation_data {
    size_t len;
    size_t align;
    unsigned int heap_id_mask;
    unsigned int flags;
    int handle;
};
struct mtk_ion_fd_data { int handle; int fd; };
struct mtk_ion_handle_data { int handle; };
#define ION_IOC_ALLOC _IOWR('I', 0, struct mtk_ion_allocation_data)
#define ION_IOC_FREE  _IOWR('I', 1, struct mtk_ion_handle_data)
#define ION_IOC_SHARE _IOWR('I', 4, struct mtk_ion_fd_data)

typedef struct {
    int ion_fd;
    int vfd;
    int w;
    int h;
    int ho, hc;
    int fd_o, fd_c;
    size_t osz, csz;
    uint8_t *out_ptr;
    uint8_t *cap_ptr;
} hwjpeg_ctx_t;

static int ion_alloc(int ion_fd, size_t len, int *out_handle) {
    struct mtk_ion_allocation_data a = { .len = len, .align = 4096, .heap_id_mask = 0x400, .flags = 0, .handle = 0 };
    if (ioctl(ion_fd, ION_IOC_ALLOC, &a) < 0) return -1;
    struct mtk_ion_fd_data s = { .handle = a.handle, .fd = -1 };
    if (ioctl(ion_fd, ION_IOC_SHARE, &s) < 0) {
        struct mtk_ion_handle_data hd = { a.handle };
        ioctl(ion_fd, ION_IOC_FREE, &hd);
        return -1;
    }
    *out_handle = a.handle;
    return s.fd;
}

hwjpeg_ctx_t *hwjpeg_create(const char *dev, int w, int h) {
    hwjpeg_ctx_t *c = calloc(1, sizeof(*c));
    if (!c) return NULL;
    c->w = w; c->h = h;
    c->ion_fd = open("/dev/ion", O_RDWR);
    c->vfd = open(dev ? dev : "/dev/video3", O_RDWR);
    if (c->ion_fd < 0 || c->vfd < 0) goto fail;

    struct v4l2_format out_fmt = {0}, cap_fmt = {0};
    out_fmt.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
    out_fmt.fmt.pix_mp.width = w; out_fmt.fmt.pix_mp.height = h;
    out_fmt.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_YUYV;
    out_fmt.fmt.pix_mp.field = V4L2_FIELD_NONE;
    out_fmt.fmt.pix_mp.num_planes = 1;
    if (ioctl(c->vfd, VIDIOC_S_FMT, &out_fmt) < 0) goto fail;

    cap_fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    cap_fmt.fmt.pix_mp.width = w; cap_fmt.fmt.pix_mp.height = h;
    cap_fmt.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_JPEG;
    cap_fmt.fmt.pix_mp.field = V4L2_FIELD_NONE;
    cap_fmt.fmt.pix_mp.num_planes = 1;
    if (ioctl(c->vfd, VIDIOC_S_FMT, &cap_fmt) < 0) goto fail;

    c->osz = out_fmt.fmt.pix_mp.plane_fmt[0].sizeimage;
    c->csz = (size_t)w * (size_t)h;
    c->fd_o = ion_alloc(c->ion_fd, c->osz, &c->ho);
    c->fd_c = ion_alloc(c->ion_fd, c->csz, &c->hc);
    if (c->fd_o < 0 || c->fd_c < 0) goto fail;

    c->out_ptr = mmap(NULL, c->osz, PROT_READ | PROT_WRITE, MAP_SHARED, c->fd_o, 0);
    c->cap_ptr = mmap(NULL, c->csz, PROT_READ | PROT_WRITE, MAP_SHARED, c->fd_c, 0);
    if (c->out_ptr == MAP_FAILED || c->cap_ptr == MAP_FAILED) goto fail;

    struct v4l2_requestbuffers ro = {1, V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, V4L2_MEMORY_DMABUF};
    struct v4l2_requestbuffers rc = {1, V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE, V4L2_MEMORY_DMABUF};
    if (ioctl(c->vfd, VIDIOC_REQBUFS, &ro) < 0) goto fail;
    if (ioctl(c->vfd, VIDIOC_REQBUFS, &rc) < 0) goto fail;

    int to = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, tc = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    if (ioctl(c->vfd, VIDIOC_STREAMON, &to) < 0) goto fail;
    if (ioctl(c->vfd, VIDIOC_STREAMON, &tc) < 0) goto fail;
    return c;
fail:
    if (c->vfd >= 0) close(c->vfd);
    if (c->ion_fd >= 0) close(c->ion_fd);
    free(c);
    return NULL;
}

int hwjpeg_encode_rgba(hwjpeg_ctx_t *c, const uint8_t *rgba, uint8_t *dst, int max_dst) {
    if (!c || !rgba || !dst) return -1;
    int n = c->w * c->h;
    uint8_t *yuyv = c->out_ptr;
    for (int i = 0; i < n; i += 2) {
        int r0 = rgba[i*4+0], g0 = rgba[i*4+1], b0 = rgba[i*4+2];
        int r1 = rgba[i*4+4], g1 = rgba[i*4+5], b1 = rgba[i*4+6];
        int y0 = ( 66*r0 + 129*g0 +  25*b0 + 128) >> 8; y0 += 16;
        int y1 = ( 66*r1 + 129*g1 +  25*b1 + 128) >> 8; y1 += 16;
        int ra = (r0 + r1) >> 1, ga = (g0 + g1) >> 1, ba = (b0 + b1) >> 1;
        int u  = (-38*ra -  74*ga + 112*ba + 128) >> 8; u  += 128;
        int v  = (112*ra -  94*ga -  18*ba + 128) >> 8; v  += 128;
        yuyv[i*2+0] = (uint8_t)(y0 < 0 ? 0 : (y0 > 255 ? 255 : y0));
        yuyv[i*2+1] = (uint8_t)(u  < 0 ? 0 : (u  > 255 ? 255 : u));
        yuyv[i*2+2] = (uint8_t)(y1 < 0 ? 0 : (y1 > 255 ? 255 : y1));
        yuyv[i*2+3] = (uint8_t)(v  < 0 ? 0 : (v  > 255 ? 255 : v));
    }

    struct v4l2_plane po = {0}, pc = {0};
    po.m.fd = c->fd_o; po.length = c->osz; po.bytesused = c->osz;
    pc.m.fd = c->fd_c; pc.length = c->csz;
    struct v4l2_buffer bo = {.type=V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,.memory=V4L2_MEMORY_DMABUF,.length=1,.m.planes=&po};
    struct v4l2_buffer bc = {.type=V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE,.memory=V4L2_MEMORY_DMABUF,.length=1,.m.planes=&pc};
    if (ioctl(c->vfd, VIDIOC_QBUF, &bo) < 0) return -2;
    if (ioctl(c->vfd, VIDIOC_QBUF, &bc) < 0) return -3;
    if (ioctl(c->vfd, VIDIOC_DQBUF, &bo) < 0) return -4;
    if (ioctl(c->vfd, VIDIOC_DQBUF, &bc) < 0) return -5;

    int len = (int)pc.bytesused;
    if (len > max_dst) len = max_dst;
    // Trim trailing 0x00 padding after JPEG EOI (0xFF 0xD9)
    while (len >= 2 && !(c->cap_ptr[len-2] == 0xFF && c->cap_ptr[len-1] == 0xD9)) {
        if (c->cap_ptr[len-1] != 0x00) break;
        len--;
    }
    memcpy(dst, c->cap_ptr, len);
    return len;
}

void hwjpeg_destroy(hwjpeg_ctx_t *c) {
    if (!c) return;
    int to = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, tc = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    ioctl(c->vfd, VIDIOC_STREAMOFF, &to);
    ioctl(c->vfd, VIDIOC_STREAMOFF, &tc);
    munmap(c->out_ptr, c->osz);
    munmap(c->cap_ptr, c->csz);
    close(c->fd_o); close(c->fd_c);
    struct mtk_ion_handle_data hd1 = {c->ho}, hd2 = {c->hc};
    ioctl(c->ion_fd, ION_IOC_FREE, &hd1);
    ioctl(c->ion_fd, ION_IOC_FREE, &hd2);
    close(c->vfd); close(c->ion_fd);
    free(c);
}

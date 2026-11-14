#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <linux/videodev2.h>
#include <arm_neon.h>

#include <weston/weston.h>

/* MediaTek 4.14 ION structs (64-bit) */
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
    int w, h;
    int ho, hc;
    int fd_o, fd_c;
    size_t osz, csz;
    uint8_t *out_ptr;
    uint8_t *cap_ptr;
} hwjpeg_enc_t;

static int ion_alloc_dmabuf(int ion_fd, size_t len, int *out_handle) {
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

static hwjpeg_enc_t *enc_create(const char *dev, int w, int h) {
    hwjpeg_enc_t *e = calloc(1, sizeof(*e));
    if (!e) return NULL;
    e->w = w; e->h = h;
    e->ion_fd = open("/dev/ion", O_RDWR);
    e->vfd = open(dev, O_RDWR);
    if (e->ion_fd < 0 || e->vfd < 0) goto fail;

    struct v4l2_format out_fmt = {0}, cap_fmt = {0};
    out_fmt.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
    out_fmt.fmt.pix_mp.width = w;
    out_fmt.fmt.pix_mp.height = h;
    out_fmt.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_YUYV;
    out_fmt.fmt.pix_mp.field = V4L2_FIELD_NONE;
    out_fmt.fmt.pix_mp.num_planes = 1;
    if (ioctl(e->vfd, VIDIOC_S_FMT, &out_fmt) < 0) goto fail;

    cap_fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    cap_fmt.fmt.pix_mp.width = w;
    cap_fmt.fmt.pix_mp.height = h;
    cap_fmt.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_JPEG;
    cap_fmt.fmt.pix_mp.field = V4L2_FIELD_NONE;
    cap_fmt.fmt.pix_mp.num_planes = 1;
    if (ioctl(e->vfd, VIDIOC_S_FMT, &cap_fmt) < 0) goto fail;

    e->osz = out_fmt.fmt.pix_mp.plane_fmt[0].sizeimage;
    e->csz = (size_t)w * (size_t)h;
    e->fd_o = ion_alloc_dmabuf(e->ion_fd, e->osz, &e->ho);
    e->fd_c = ion_alloc_dmabuf(e->ion_fd, e->csz, &e->hc);
    if (e->fd_o < 0 || e->fd_c < 0) goto fail;

    e->out_ptr = mmap(NULL, e->osz, PROT_READ | PROT_WRITE, MAP_SHARED, e->fd_o, 0);
    e->cap_ptr = mmap(NULL, e->csz, PROT_READ | PROT_WRITE, MAP_SHARED, e->fd_c, 0);
    if (e->out_ptr == MAP_FAILED || e->cap_ptr == MAP_FAILED) goto fail;

    struct v4l2_requestbuffers ro = { .count = 1, .type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, .memory = V4L2_MEMORY_DMABUF };
    struct v4l2_requestbuffers rc = { .count = 1, .type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE, .memory = V4L2_MEMORY_DMABUF };
    if (ioctl(e->vfd, VIDIOC_REQBUFS, &ro) < 0) goto fail;
    if (ioctl(e->vfd, VIDIOC_REQBUFS, &rc) < 0) goto fail;

    int to = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, tc = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    if (ioctl(e->vfd, VIDIOC_STREAMON, &to) < 0) goto fail;
    if (ioctl(e->vfd, VIDIOC_STREAMON, &tc) < 0) goto fail;
    return e;
fail:
    if (e->vfd >= 0) close(e->vfd);
    if (e->ion_fd >= 0) close(e->ion_fd);
    free(e);
    return NULL;
}

static void enc_destroy(hwjpeg_enc_t *e) {
    if (!e) return;
    int to = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, tc = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    ioctl(e->vfd, VIDIOC_STREAMOFF, &to);
    ioctl(e->vfd, VIDIOC_STREAMOFF, &tc);
    munmap(e->out_ptr, e->osz);
    munmap(e->cap_ptr, e->csz);
    close(e->fd_o); close(e->fd_c);
    struct mtk_ion_handle_data hd1 = {e->ho}, hd2 = {e->hc};
    ioctl(e->ion_fd, ION_IOC_FREE, &hd1);
    ioctl(e->ion_fd, ION_IOC_FREE, &hd2);
    close(e->vfd); close(e->ion_fd);
    free(e);
}

/* NEON accelerated BGRA (PIXMAN_a8r8g8b8 on little-endian: B, G, R, A) -> YUYV */
static void bgra_to_yuyv_neon(const uint8_t *src, uint8_t *dst, int w, int h, int flip_y) {
    const uint8x8_t v_y_r = vdup_n_u8(66);
    const uint8x8_t v_y_g = vdup_n_u8(129);
    const uint8x8_t v_y_b = vdup_n_u8(25);
    const uint16x8_t v_c16 = vdupq_n_u16(128 + (16 << 8));

    for (int y = 0; y < h; y++) {
        int sy = flip_y ? (h - 1 - y) : y;
        const uint8_t *s = src + (size_t)sy * (size_t)w * 4;
        uint8_t *d = dst + (size_t)y * (size_t)w * 2;
        int x = 0;
        for (; x + 8 <= w; x += 8) {
            uint8x8x4_t p = vld4_u8(s); // val[0]=B, val[1]=G, val[2]=R, val[3]=A
            uint16x8_t yy = vmlal_u8(v_c16, p.val[2], v_y_r);
            yy = vmlal_u8(yy, p.val[1], v_y_g);
            yy = vmlal_u8(yy, p.val[0], v_y_b);
            uint8x8_t y8 = vshrn_n_u16(yy, 8);

            // Subsample pairs for U/V (4 pairs -> 4 U, 4 V)
            // Use pairwise add on 8 pixels -> 4 averages
            uint16x4_t r2 = vpaddl_u8(p.val[2]);
            uint16x4_t g2 = vpaddl_u8(p.val[1]);
            uint16x4_t b2 = vpaddl_u8(p.val[0]);
            int16x4_t ra = vreinterpret_s16_u16(vshr_n_u16(r2, 1));
            int16x4_t ga = vreinterpret_s16_u16(vshr_n_u16(g2, 1));
            int16x4_t ba = vreinterpret_s16_u16(vshr_n_u16(b2, 1));

            int32x4_t u32 = vdupq_n_s32(128 + (128 << 8));
            u32 = vmlal_n_s16(u32, ra, -38);
            u32 = vmlal_n_s16(u32, ga, -74);
            u32 = vmlal_n_s16(u32, ba, 112);
            int16x4_t u16 = vshrn_n_s32(u32, 8);

            int32x4_t v32 = vdupq_n_s32(128 + (128 << 8));
            v32 = vmlal_n_s16(v32, ra, 112);
            v32 = vmlal_n_s16(v32, ga, -94);
            v32 = vmlal_n_s16(v32, ba, -18);
            int16x4_t v16 = vshrn_n_s32(v32, 8);

            uint8x8_t uv8 = vqmovun_s16(vcombine_s16(u16, v16)); // low4=U, high4=V
            // Interleave Y0,U0,Y1,V0 ... from y8 and uv8
            // Deinterleave y8 into even/odd
            uint8x8x2_t y_eo = vuzp_u8(y8, y8); // val[0] low4 = even Y, val[1] low4 = odd Y
            // Zip low4 U with low4 V -> u0,v0,u1,v1,u2,v2,u3,v3
            uint8x8x2_t uv_zip = vzip_u8(uv8, vext_u8(uv8, uv8, 4));
            // Zip Y0,Y1,... with U0,V0,...
            uint8x8_t y_pairs = vzip_u8(y_eo.val[0], y_eo.val[1]).val[0];
            uint8x8x2_t out_st = vzip_u8(y_pairs, uv_zip.val[0]);
            vst1_u8(d + 0, out_st.val[0]);
            vst1_u8(d + 8, out_st.val[1]);

            s += 32;
            d += 16;
        }
        for (; x < w; x += 2) {
            int b0=s[0], g0=s[1], r0=s[2], b1=s[4], g1=s[5], r1=s[6];
            int y0 = ((66*r0 + 129*g0 + 25*b0 + 128) >> 8) + 16;
            int y1 = ((66*r1 + 129*g1 + 25*b1 + 128) >> 8) + 16;
            int ra = (r0+r1)>>1, ga = (g0+g1)>>1, ba = (b0+b1)>>1;
            int u  = ((-38*ra - 74*ga + 112*ba + 128) >> 8) + 128;
            int v  = ((112*ra - 94*ga - 18*ba + 128) >> 8) + 128;
            d[0] = (uint8_t)(y0<0?0:(y0>255?255:y0));
            d[1] = (uint8_t)(u <0?0:(u >255?255:u));
            d[2] = (uint8_t)(y1<0?0:(y1>255?255:y1));
            d[3] = (uint8_t)(v <0?0:(v >255?255:v));
            s += 8; d += 4;
        }
    }
}

static int enc_encode_bgra(hwjpeg_enc_t *e, const uint8_t *bgra, int flip_y, uint8_t *dst, int max_dst) {
    bgra_to_yuyv_neon(bgra, e->out_ptr, e->w, e->h, flip_y);

    struct v4l2_plane po = {0}, pc = {0};
    po.m.fd = e->fd_o; po.length = e->osz; po.bytesused = e->osz;
    pc.m.fd = e->fd_c; pc.length = e->csz;
    struct v4l2_buffer bo = {.type=V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,.memory=V4L2_MEMORY_DMABUF,.length=1,.m.planes=&po};
    struct v4l2_buffer bc = {.type=V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE,.memory=V4L2_MEMORY_DMABUF,.length=1,.m.planes=&pc};
    if (ioctl(e->vfd, VIDIOC_QBUF, &bo) < 0) return -1;
    if (ioctl(e->vfd, VIDIOC_QBUF, &bc) < 0) return -2;
    if (ioctl(e->vfd, VIDIOC_DQBUF, &bo) < 0) return -3;
    if (ioctl(e->vfd, VIDIOC_DQBUF, &bc) < 0) return -4;

    int len = (int)pc.bytesused;
    if (len > max_dst) len = max_dst;
    while (len >= 2 && !(e->cap_ptr[len-2] == 0xFF && e->cap_ptr[len-1] == 0xD9)) {
        if (e->cap_ptr[len-1] != 0x00) break;
        len--;
    }
    memcpy(dst, e->cap_ptr, len);
    return len;
}

/* --- Weston Module State --- */
static struct {
    struct weston_compositor *ec;
    struct weston_output *output;
    struct wl_listener output_created_listener;
    struct wl_listener frame_listener;
    struct wl_listener destroy_listener;

    pthread_mutex_t mu;
    pthread_cond_t cond;
    int running;
    int flip_y;
    int w, h;
    uint8_t *staging[2];
    int write_idx;
    int ready_idx;
    int has_new_frame;

    int srv_fd;
    int client_fd;
    pthread_t worker;
} g_mod = { .srv_fd = -1, .client_fd = -1 };

static void accept_client_nonblock(void) {
    if (g_mod.srv_fd < 0) return;
    int c = accept4(g_mod.srv_fd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (c >= 0) {
        if (g_mod.client_fd >= 0) close(g_mod.client_fd);
        g_mod.client_fd = c;
    }
}

static int write_full_nb(int fd, const void *buf, size_t n) {
    const uint8_t *p = buf;
    size_t off = 0;
    int retries = 0;
    while (off < n) {
        ssize_t r = send(fd, p + off, n - off, MSG_NOSIGNAL);
        if (r > 0) { off += r; retries = 0; continue; }
        if (r < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            if (++retries > 50) return -1;
            usleep(1000);
            continue;
        }
        return -1;
    }
    return 0;
}

static void *worker_thread(void *arg) {
    (void)arg;
    int cur_w = 0, cur_h = 0;
    hwjpeg_enc_t *enc = NULL;
    uint8_t *local_bgra = NULL;
    uint8_t *jpg_buf = NULL;
    int max_jpg = 0;

    while (1) {
        pthread_mutex_lock(&g_mod.mu);
        while (g_mod.running && !g_mod.has_new_frame) {
            pthread_cond_wait(&g_mod.cond, &g_mod.mu);
        }
        if (!g_mod.running) {
            pthread_mutex_unlock(&g_mod.mu);
            break;
        }
        int idx = g_mod.ready_idx;
        int w = g_mod.w, h = g_mod.h, flip = g_mod.flip_y;
        g_mod.has_new_frame = 0;
        if (w != cur_w || h != cur_h) {
            free(local_bgra);
            free(jpg_buf);
            enc_destroy(enc);
            cur_w = w; cur_h = h;
            local_bgra = malloc((size_t)w * (size_t)h * 4);
            max_jpg = w * h;
            jpg_buf = malloc(max_jpg);
            enc = enc_create("/dev/video3", w, h);
            if (!enc) enc = enc_create("/dev/video4", w, h);
        }
        if (local_bgra && g_mod.staging[idx]) {
            memcpy(local_bgra, g_mod.staging[idx], (size_t)w * (size_t)h * 4);
        }
        pthread_mutex_unlock(&g_mod.mu);

        accept_client_nonblock();
        if (enc && local_bgra && jpg_buf) {
            int jlen = enc_encode_bgra(enc, local_bgra, flip, jpg_buf, max_jpg);
            if (jlen > 0) {
                /* Also write /dev/shm/weston_hw.jpg for instant curl/HTTP checks */
                int sfd = open("/dev/shm/.hw_tmp.jpg", O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (sfd >= 0) {
                    ssize_t wr = write(sfd, jpg_buf, jlen);
                    (void)wr;
                    close(sfd);
                    rename("/dev/shm/.hw_tmp.jpg", "/dev/shm/weston_hw.jpg");
                }
                if (g_mod.client_fd >= 0) {
                    uint32_t hdr = (uint32_t)jlen;
                    if (write_full_nb(g_mod.client_fd, &hdr, 4) < 0 ||
                        write_full_nb(g_mod.client_fd, jpg_buf, jlen) < 0) {
                        close(g_mod.client_fd);
                        g_mod.client_fd = -1;
                    }
                }
            }
        }
    }
    free(local_bgra);
    free(jpg_buf);
    enc_destroy(enc);
    return NULL;
}

static uint64_t g_last_cap_ns = 0;

static void on_output_frame(struct wl_listener *listener, void *data) {
    (void)listener; (void)data;
    struct weston_output *output = g_mod.output;
    if (!output || !output->current_mode || !g_mod.ec || !g_mod.ec->renderer)
        return;

    /* Cap capture rate at ~45 FPS to keep Mali readback lightweight */
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t now_ns = (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
    if (now_ns - g_last_cap_ns < 16000000ULL)
        return;
    g_last_cap_ns = now_ns;

    int w = output->current_mode->width;
    int h = output->current_mode->height;
    if (w <= 0 || h <= 0) return;

    pthread_mutex_lock(&g_mod.mu);
    if (w != g_mod.w || h != g_mod.h) {
        free(g_mod.staging[0]);
        free(g_mod.staging[1]);
        g_mod.staging[0] = malloc((size_t)w * (size_t)h * 4);
        g_mod.staging[1] = malloc((size_t)w * (size_t)h * 4);
        g_mod.w = w;
        g_mod.h = h;
    }
    int idx = g_mod.write_idx;
    uint8_t *dst = g_mod.staging[idx];
    pthread_mutex_unlock(&g_mod.mu);

    if (!dst) return;
    if (g_mod.ec->renderer->read_pixels(output, PIXMAN_a8r8g8b8, dst, 0, 0, w, h) == 0) {
        pthread_mutex_lock(&g_mod.mu);
        g_mod.ready_idx = idx;
        g_mod.write_idx = 1 - idx;
        g_mod.has_new_frame = 1;
        pthread_cond_signal(&g_mod.cond);
        pthread_mutex_unlock(&g_mod.mu);
    }
}

static void attach_output(struct weston_output *output) {
    if (g_mod.frame_listener.notify)
        wl_list_remove(&g_mod.frame_listener.link);
    g_mod.output = output;
    g_mod.frame_listener.notify = on_output_frame;
    wl_signal_add(&output->frame_signal, &g_mod.frame_listener);
    weston_log("weston_hwjpeg: attached to output '%s' (%dx%d)\n",
               output->name ? output->name : "?",
               output->current_mode ? output->current_mode->width : 0,
               output->current_mode ? output->current_mode->height : 0);
}

static void on_output_created(struct wl_listener *listener, void *data) {
    (void)listener;
    attach_output((struct weston_output *)data);
}

static void on_destroy(struct wl_listener *listener, void *data) {
    (void)listener; (void)data;
    pthread_mutex_lock(&g_mod.mu);
    g_mod.running = 0;
    pthread_cond_broadcast(&g_mod.cond);
    pthread_mutex_unlock(&g_mod.mu);
    pthread_join(g_mod.worker, NULL);
    if (g_mod.srv_fd >= 0) close(g_mod.srv_fd);
    if (g_mod.client_fd >= 0) close(g_mod.client_fd);
    free(g_mod.staging[0]);
    free(g_mod.staging[1]);
}

WL_EXPORT int wet_module_init(struct weston_compositor *ec, int *argc, char *argv[]) {
    (void)argc; (void)argv;
    g_mod.ec = ec;
    g_mod.flip_y = (getenv("HWJPEG_FLIP_Y") && atoi(getenv("HWJPEG_FLIP_Y")) == 1) ? 1 : 0;
    pthread_mutex_init(&g_mod.mu, NULL);
    pthread_cond_init(&g_mod.cond, NULL);
    g_mod.running = 1;

    const char *sock_path = getenv("HWJPEG_SOCK") ?: "/tmp/weston_hwjpeg.sock";
    unlink(sock_path);
    g_mod.srv_fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (g_mod.srv_fd >= 0) {
        struct sockaddr_un addr = {0};
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, sock_path, sizeof(addr.sun_path) - 1);
        if (bind(g_mod.srv_fd, (struct sockaddr *)&addr, sizeof(addr)) == 0) {
            listen(g_mod.srv_fd, 4);
            chmod(sock_path, 0666);
        }
    }

    pthread_create(&g_mod.worker, NULL, worker_thread, NULL);

    g_mod.destroy_listener.notify = on_destroy;
    wl_signal_add(&ec->destroy_signal, &g_mod.destroy_listener);

    g_mod.output_created_listener.notify = on_output_created;
    wl_signal_add(&ec->output_created_signal, &g_mod.output_created_listener);

    struct weston_output *output;
    wl_list_for_each(output, &ec->output_list, link) {
        attach_output(output);
        break;
    }

    weston_log("weston_hwjpeg: initialized (NEON + /dev/video3 ION 0x400)\n");
    return 0;
}

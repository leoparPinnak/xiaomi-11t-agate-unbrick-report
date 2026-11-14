#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <dlfcn.h>
#include <pthread.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <linux/fb.h>
#include <linux/input.h>

#define SCR_W 1080
#define SCR_H 2400
#define FB_STRIDE_PX 1088
#define XWD_PATH "/dev/shm/xfb/Xvfb_screen0"

static volatile int g_running = 1;
static volatile int g_screen_on = 1;
static pthread_mutex_t g_scr_mu = PTHREAD_MUTEX_INITIALIZER;

static void write_sys(const char *path, const char *val) {
    int fd = open(path, O_WRONLY);
    if (fd >= 0) {
        ssize_t r = write(fd, val, strlen(val));
        (void)r;
        close(fd);
    }
}

static void set_screen(int on) {
    pthread_mutex_lock(&g_scr_mu);
    g_screen_on = on ? 1 : 0;
    if (g_screen_on) {
        write_sys("/sys/class/graphics/fb0/blank", "0\n");
        write_sys("/sys/class/leds/lcd-backlight/brightness", "1200\n");
    } else {
        write_sys("/sys/class/leds/lcd-backlight/brightness", "0\n");
        write_sys("/sys/class/graphics/fb0/blank", "1\n");
    }
    pthread_mutex_unlock(&g_scr_mu);
}

static void *power_thread(void *arg) {
    (void)arg;
    int fd = open("/dev/input/event1", O_RDONLY);
    if (fd < 0) return NULL;
    struct input_event ev;
    while (g_running) {
        ssize_t n = read(fd, &ev, sizeof(ev));
        if (n == (ssize_t)sizeof(ev)) {
            if (ev.type == EV_KEY && ev.code == KEY_POWER && ev.value == 1) {
                set_screen(!g_screen_on);
            }
        } else if (n <= 0) {
            usleep(100000);
        }
    }
    close(fd);
    return NULL;
}

static void *fifo_thread(void *arg) {
    (void)arg;
    mkfifo("/run/fbui.ctl", 0622);
    chmod("/run/fbui.ctl", 0622);
    while (g_running) {
        int fd = open("/run/fbui.ctl", O_RDONLY);
        if (fd < 0) { usleep(200000); continue; }
        char buf[64];
        ssize_t n = read(fd, buf, sizeof(buf) - 1);
        close(fd);
        if (n > 0) {
            buf[n] = 0;
            if (strstr(buf, "on")) set_screen(1);
            else if (strstr(buf, "off")) set_screen(0);
            else if (strstr(buf, "toggle")) set_screen(!g_screen_on);
        }
    }
    return NULL;
}

static void *touch_thread(void *arg) {
    const char *disp_name = (const char *)arg;
    void *hx11 = dlopen("libX11.so.6", RTLD_NOW | RTLD_GLOBAL);
    void *hxtst = dlopen("libXtst.so.6", RTLD_NOW);
    if (!hx11 || !hxtst) {
        fprintf(stderr, "fb_xfce_bridge: failed to dlopen libX11/libXtst\n");
        return NULL;
    }
    void *(*pXOpenDisplay)(const char *) = dlsym(hx11, "XOpenDisplay");
    int (*pXFlush)(void *) = dlsym(hx11, "XFlush");
    int (*pXTestFakeMotionEvent)(void *, int, int, int, unsigned long) = dlsym(hxtst, "XTestFakeMotionEvent");
    int (*pXTestFakeButtonEvent)(void *, unsigned int, int, unsigned long) = dlsym(hxtst, "XTestFakeButtonEvent");
    if (!pXOpenDisplay || !pXFlush || !pXTestFakeMotionEvent || !pXTestFakeButtonEvent) return NULL;

    void *dpy = NULL;
    for (int i = 0; i < 50 && g_running; i++) {
        dpy = pXOpenDisplay(disp_name);
        if (dpy) break;
        usleep(100000);
    }
    if (!dpy) return NULL;

    int fd = -1;
    for (int i = 0; i < 20 && g_running; i++) {
        fd = open("/dev/input/event4", O_RDONLY);
        if (fd >= 0) break;
        usleep(200000);
    }
    if (fd < 0) return NULL;

    int cur_x = 540, cur_y = 1200;
    int touching = 0;
    int slot = 0;
    struct input_event ev;
    while (g_running) {
        ssize_t n = read(fd, &ev, sizeof(ev));
        if (n != (ssize_t)sizeof(ev)) { usleep(10000); continue; }
        if (!g_screen_on) continue;

        if (ev.type == EV_ABS) {
            if (ev.code == ABS_MT_SLOT) slot = ev.value;
            else if (slot == 0 && ev.code == ABS_MT_POSITION_X) cur_x = ev.value / 10;
            else if (slot == 0 && ev.code == ABS_MT_POSITION_Y) cur_y = ev.value / 10;
            else if (slot == 0 && ev.code == ABS_MT_TRACKING_ID) {
                if (ev.value >= 0 && !touching) {
                    touching = 1;
                    if (cur_x < 0) cur_x = 0; if (cur_x >= SCR_W) cur_x = SCR_W - 1;
                    if (cur_y < 0) cur_y = 0; if (cur_y >= SCR_H) cur_y = SCR_H - 1;
                    pXTestFakeMotionEvent(dpy, -1, cur_x, cur_y, 0);
                    pXTestFakeButtonEvent(dpy, 1, 1, 0);
                    pXFlush(dpy);
                } else if (ev.value < 0 && touching) {
                    touching = 0;
                    pXTestFakeButtonEvent(dpy, 1, 0, 0);
                    pXFlush(dpy);
                }
            }
        } else if (ev.type == EV_KEY && ev.code == BTN_TOUCH) {
            if (ev.value == 1 && !touching) {
                touching = 1;
                pXTestFakeMotionEvent(dpy, -1, cur_x, cur_y, 0);
                pXTestFakeButtonEvent(dpy, 1, 1, 0);
                pXFlush(dpy);
            } else if (ev.value == 0 && touching) {
                touching = 0;
                pXTestFakeButtonEvent(dpy, 1, 0, 0);
                pXFlush(dpy);
            }
        } else if (ev.type == EV_SYN && ev.code == SYN_REPORT && touching) {
            if (cur_x < 0) cur_x = 0; if (cur_x >= SCR_W) cur_x = SCR_W - 1;
            if (cur_y < 0) cur_y = 0; if (cur_y >= SCR_H) cur_y = SCR_H - 1;
            pXTestFakeMotionEvent(dpy, -1, cur_x, cur_y, 0);
            pXFlush(dpy);
        }
    }
    close(fd);
    return NULL;
}

static void on_sig(int s) { (void)s; g_running = 0; }

static uint32_t read_be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

int main(int argc, char **argv) {
    const char *disp = argc > 1 ? argv[1] : ":0";
    signal(SIGTERM, on_sig);
    signal(SIGINT, on_sig);

    int xfd = -1;
    for (int i = 0; i < 60 && g_running; i++) {
        xfd = open(XWD_PATH, O_RDONLY);
        if (xfd >= 0) break;
        usleep(100000);
    }
    if (xfd < 0) { perror("open Xvfb_screen0"); return 1; }

    struct stat st;
    fstat(xfd, &st);
    uint8_t *xmap = mmap(NULL, st.st_size, PROT_READ, MAP_SHARED, xfd, 0);
    if (xmap == MAP_FAILED) { perror("mmap xwd"); return 2; }

    uint32_t hdr_sz = read_be32(xmap + 0);
    uint32_t ncolors = read_be32(xmap + 76);
    size_t pix_off = hdr_sz + ncolors * 12;
    const uint32_t *src = (const uint32_t *)(xmap + pix_off);

    int fbfd = open("/dev/fb0", O_RDWR);
    if (fbfd < 0) { perror("open /dev/fb0"); return 3; }

    size_t fb_bytes = (size_t)FB_STRIDE_PX * SCR_H * 4;
    uint32_t *fb_map = mmap(NULL, fb_bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fbfd, 0);
    uint32_t *prev = calloc(SCR_W * SCR_H, 4);

    struct fb_var_screeninfo vinfo;
    ioctl(fbfd, FBIOGET_VSCREENINFO, &vinfo);

    set_screen(1);

    pthread_t th_pwr, th_fifo, th_tch;
    pthread_create(&th_pwr, NULL, power_thread, NULL);
    pthread_create(&th_fifo, NULL, fifo_thread, NULL);
    pthread_create(&th_tch, NULL, touch_thread, (void *)disp);

    while (g_running) {
        if (g_screen_on) {
            int dirty = 0;
            for (int y = 0; y < SCR_H; y++) {
                const uint32_t *srow = src + y * SCR_W;
                uint32_t *prow = prev + y * SCR_W;
                if (memcmp(srow, prow, SCR_W * 4) != 0) {
                    memcpy(prow, srow, SCR_W * 4);
                    uint32_t *drow = (fb_map != MAP_FAILED) ? (fb_map + y * FB_STRIDE_PX) : NULL;
                    if (drow) {
                        for (int x = 0; x < SCR_W; x++) {
                            uint32_t p = srow[x]; /* BGRX little-endian: B=low byte, R=byte2 */
                            drow[x] = (p & 0x0000FF00U) | ((p & 0xFFU) << 16) | ((p >> 16) & 0xFFU) | 0xFF000000U;
                        }
                    }
                    dirty = 1;
                }
            }
            if (dirty) {
                vinfo.xoffset = 0;
                vinfo.yoffset = 0;
                ioctl(fbfd, FBIOPAN_DISPLAY, &vinfo);
            }
        }
        usleep(33000);
    }

    set_screen(0);
    free(prev);
    munmap(xmap, st.st_size);
    if (fb_map != MAP_FAILED) munmap(fb_map, fb_bytes);
    close(fbfd);
    close(xfd);
    return 0;
}

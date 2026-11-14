#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <dlfcn.h>
#include <pthread.h>
#include <signal.h>
#include <time.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <linux/videodev2.h>
#include <arm_neon.h>

#define FB_W 1080
#define FB_H 2400
#define FB_STRIDE_PX 1088
#define XWD_PATH "/dev/shm/xfb/Xvfb_screen0"
#define XFCE_SOCK "/tmp/xfce_hwjpeg.sock"
#define XFCE_SHM_JPG "/dev/shm/xfce_hw.jpg"
#define UDP_PORT 9900
#define UDP_CHUNK_PAYLOAD 1360

/* MediaTek Android ION ioctl (MTK 4.14) */
struct mtk_ion_alloc_data { size_t len; size_t align; unsigned int heap_id_mask; unsigned int flags; int handle; };
struct mtk_ion_fd_data    { int handle; int fd; };
struct mtk_ion_handle_data{ int handle; };
#define ION_IOC_ALLOC _IOWR('I', 0, struct mtk_ion_alloc_data)
#define ION_IOC_FREE  _IOWR('I', 1, struct mtk_ion_handle_data)
#define ION_IOC_SHARE _IOWR('I', 4, struct mtk_ion_fd_data)
#define ION_HEAP_MULTIMEDIA_MASK (1u << 10)

/* Binary-compatible XFixesCursorImage (LP64 aarch64) */
typedef struct {
    short x, y;
    unsigned short width, height;
    unsigned short xhot, yhot;
    unsigned long cursor_serial;
    unsigned long *pixels;
} my_XFixesCursorImage;

#pragma pack(push, 1)
typedef struct {
    char magic[4];      /* "AGTU" */
    uint32_t frame_id;
    uint32_t total_size;
    uint16_t chunk_idx;
    uint16_t chunk_cnt;
} udp_chunk_hdr_t;
#pragma pack(pop)

static volatile int g_running = 1;
static volatile int g_screen_on = 1;
static int g_landscape = 1;
static int g_xv_w = 2400;
static int g_xv_h = 1080;

static pthread_mutex_t g_scr_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t g_enc_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  g_enc_cv = PTHREAD_COND_INITIALIZER;
static uint32_t *g_enc_buf = NULL;
static int g_enc_ready = 0;

static pthread_mutex_t g_cli_mu = PTHREAD_MUTEX_INITIALIZER;
static int g_srv_fd = -1;
static int g_cli_fd = -1;
static volatile int g_force_frame = 0;

/* UDP state */
static int g_udp_fd = -1;
static pthread_mutex_t g_udp_mu = PTHREAD_MUTEX_INITIALIZER;
static struct sockaddr_in g_udp_cli;
static int g_udp_has_cli = 0;
static uint64_t g_udp_last_hello_ms = 0;
static uint32_t g_udp_frame_id = 0;

static inline uint64_t now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000ULL + ts.tv_nsec / 1000000ULL;
}

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
            if (ev.type == EV_KEY && ev.code == KEY_POWER && ev.value == 1)
                set_screen(!g_screen_on);
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

static void map_touch(int raw_x_px, int raw_y_px, int *out_x, int *out_y) {
    if (g_landscape) {
        int vx = (FB_H - 1) - raw_y_px;
        int vy = raw_x_px;
        if (vx < 0) vx = 0;
        if (vx >= FB_H) vx = FB_H - 1;
        if (vy < 0) vy = 0;
        if (vy >= FB_W) vy = FB_W - 1;
        *out_x = vx;
        *out_y = vy;
    } else {
        int vx = raw_x_px, vy = raw_y_px;
        if (vx < 0) vx = 0;
        if (vx >= FB_W) vx = FB_W - 1;
        if (vy < 0) vy = 0;
        if (vy >= FB_H) vy = FB_H - 1;
        *out_x = vx;
        *out_y = vy;
    }
}

static void *touch_thread(void *arg) {
    const char *disp_name = (const char *)arg;
    void *hx11 = dlopen("libX11.so.6", RTLD_NOW | RTLD_GLOBAL);
    void *hxtst = dlopen("libXtst.so.6", RTLD_NOW);
    if (!hx11 || !hxtst) return NULL;

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

    int raw_x = 540, raw_y = 1200, touching = 0, slot = 0;
    struct input_event ev;
    while (g_running) {
        ssize_t n = read(fd, &ev, sizeof(ev));
        if (n != (ssize_t)sizeof(ev)) { usleep(10000); continue; }
        if (!g_screen_on) continue;

        if (ev.type == EV_ABS) {
            if (ev.code == ABS_MT_SLOT) slot = ev.value;
            else if (slot == 0 && ev.code == ABS_MT_POSITION_X) raw_x = ev.value / 10;
            else if (slot == 0 && ev.code == ABS_MT_POSITION_Y) raw_y = ev.value / 10;
            else if (slot == 0 && ev.code == ABS_MT_TRACKING_ID) {
                int mx, my;
                map_touch(raw_x, raw_y, &mx, &my);
                if (ev.value >= 0 && !touching) {
                    touching = 1;
                    pXTestFakeMotionEvent(dpy, -1, mx, my, 0);
                    pXTestFakeButtonEvent(dpy, 1, 1, 0);
                    pXFlush(dpy);
                } else if (ev.value < 0 && touching) {
                    touching = 0;
                    pXTestFakeButtonEvent(dpy, 1, 0, 0);
                    pXFlush(dpy);
                }
            }
        } else if (ev.type == EV_KEY && ev.code == BTN_TOUCH) {
            int mx, my;
            map_touch(raw_x, raw_y, &mx, &my);
            if (ev.value == 1 && !touching) {
                touching = 1;
                pXTestFakeMotionEvent(dpy, -1, mx, my, 0);
                pXTestFakeButtonEvent(dpy, 1, 1, 0);
                pXFlush(dpy);
            } else if (ev.value == 0 && touching) {
                touching = 0;
                pXTestFakeButtonEvent(dpy, 1, 0, 0);
                pXFlush(dpy);
            }
        } else if (ev.type == EV_SYN && ev.code == SYN_REPORT && touching) {
            int mx, my;
            map_touch(raw_x, raw_y, &mx, &my);
            pXTestFakeMotionEvent(dpy, -1, mx, my, 0);
            pXFlush(dpy);
        }
    }
    close(fd);
    return NULL;
}

/* --- Direct C UDP Input Receiver (0-copy latency for mouse/drag/keyboard/Turkish) --- */
typedef struct { uint32_t cp; uint32_t kc; int shift; } tr_slot_t;
static const struct { uint32_t kc; unsigned long lo; unsigned long hi; } g_tr_map[6] = {
    { 154, 0x01ba, 0x01aa }, /* ş Ş */
    { 168, 0x02bb, 0x02ab }, /* ğ Ğ */
    { 178, 0x00fc, 0x00dc }, /* ü Ü */
    { 183, 0x02b9, 0x02a9 }, /* ı İ */
    { 184, 0x00f6, 0x00d6 }, /* ö Ö */
    { 197, 0x00e7, 0x00c7 }, /* ç Ç */
};
static const tr_slot_t g_tr_cp[12] = {
    { 0x015f, 154, 0 }, { 0x015e, 154, 1 },
    { 0x011f, 168, 0 }, { 0x011e, 168, 1 },
    { 0x00fc, 178, 0 }, { 0x00dc, 178, 1 },
    { 0x0131, 183, 0 }, { 0x0130, 183, 1 },
    { 0x00f6, 184, 0 }, { 0x00d6, 184, 1 },
    { 0x00e7, 197, 0 }, { 0x00c7, 197, 1 },
};

static const char *ascii_sym(char ch, int *need_shift) {
    *need_shift = 0;
    if (ch >= 'a' && ch <= 'z') return NULL;
    if (ch >= 'A' && ch <= 'Z') { *need_shift = 1; return NULL; }
    if (ch >= '0' && ch <= '9') return NULL;
    switch (ch) {
        case ' ': return "space"; case '\n': return "Return"; case '\t': return "Tab";
        case '.': return "period"; case ',': return "comma"; case '/': return "slash";
        case '?': *need_shift = 1; return "slash";
        case ':': *need_shift = 1; return "semicolon";
        case ';': return "semicolon";
        case '-': return "minus"; case '_': *need_shift = 1; return "minus";
        case '=': return "equal"; case '+': *need_shift = 1; return "equal";
        case '!': *need_shift = 1; return "1"; case '@': *need_shift = 1; return "2";
        case '#': *need_shift = 1; return "3"; case '$': *need_shift = 1; return "4";
        case '%': *need_shift = 1; return "5"; case '^': *need_shift = 1; return "6";
        case '&': *need_shift = 1; return "7"; case '*': *need_shift = 1; return "8";
        case '(': *need_shift = 1; return "9"; case ')': *need_shift = 1; return "0";
        case '[': return "bracketleft"; case ']': return "bracketright";
        case '{': *need_shift = 1; return "bracketleft"; case '}': *need_shift = 1; return "bracketright";
        case '\'': return "apostrophe"; case '"': *need_shift = 1; return "apostrophe";
        case '\\': return "backslash"; case '|': *need_shift = 1; return "backslash";
        case '<': *need_shift = 1; return "comma"; case '>': *need_shift = 1; return "period";
        case '`': return "grave"; case '~': *need_shift = 1; return "grave";
    }
    return NULL;
}

static void *udp_rx_thread(void *arg) {
    const char *disp_name = (const char *)arg;
    void *hx11 = dlopen("libX11.so.6", RTLD_NOW | RTLD_GLOBAL);
    void *hxtst = dlopen("libXtst.so.6", RTLD_NOW);
    if (!hx11 || !hxtst) return NULL;

    void *(*pXOpenDisplay)(const char *) = dlsym(hx11, "XOpenDisplay");
    int (*pXFlush)(void *) = dlsym(hx11, "XFlush");
    int (*pXSync)(void *, int) = dlsym(hx11, "XSync");
    unsigned int (*pXKeysymToKeycode)(void *, unsigned long) = dlsym(hx11, "XKeysymToKeycode");
    unsigned long (*pXStringToKeysym)(const char *) = dlsym(hx11, "XStringToKeysym");
    int (*pXChangeKeyboardMapping)(void *, int, int, unsigned long *, int) = dlsym(hx11, "XChangeKeyboardMapping");
    int (*pXTestMotion)(void *, int, int, int, unsigned long) = dlsym(hxtst, "XTestFakeMotionEvent");
    int (*pXTestBtn)(void *, unsigned int, int, unsigned long) = dlsym(hxtst, "XTestFakeButtonEvent");
    int (*pXTestKey)(void *, unsigned int, int, unsigned long) = dlsym(hxtst, "XTestFakeKeyEvent");

    void *dpy = NULL;
    for (int i = 0; i < 50 && g_running; i++) {
        dpy = pXOpenDisplay(disp_name);
        if (dpy) break;
        usleep(100000);
    }
    if (!dpy) return NULL;

    for (int i = 0; i < 6; i++) {
        unsigned long arr[2] = { g_tr_map[i].lo, g_tr_map[i].hi };
        pXChangeKeyboardMapping(dpy, (int)g_tr_map[i].kc, 2, arr, 1);
    }
    pXSync(dpy, 0);

    unsigned int kc_ctrl  = pXKeysymToKeycode(dpy, 0xFFE3);
    unsigned int kc_alt   = pXKeysymToKeycode(dpy, 0xFFE9);
    unsigned int kc_shift = pXKeysymToKeycode(dpy, 0xFFE1);
    unsigned int kc_meta  = pXKeysymToKeycode(dpy, 0xFFEB);

    uint8_t buf[2048];
    struct sockaddr_in from;
    while (g_running && g_udp_fd >= 0) {
        socklen_t flen = sizeof(from);
        ssize_t n = recvfrom(g_udp_fd, buf, sizeof(buf), 0, (struct sockaddr *)&from, &flen);
        if (n < 4) { usleep(5000); continue; }

        if (memcmp(buf, "AGTH", 4) == 0) {
            pthread_mutex_lock(&g_udp_mu);
            g_udp_cli = from;
            g_udp_has_cli = 1;
            g_udp_last_hello_ms = now_ms();
            g_force_frame = 1;
            pthread_mutex_unlock(&g_udp_mu);

            /* Reply AGTS + width(u16) + height(u16) + screen_on(u8) */
            uint8_t ack[9];
            memcpy(ack, "AGTS", 4);
            ack[4] = (uint8_t)(g_xv_w & 0xff); ack[5] = (uint8_t)((g_xv_w >> 8) & 0xff);
            ack[6] = (uint8_t)(g_xv_h & 0xff); ack[7] = (uint8_t)((g_xv_h >> 8) & 0xff);
            ack[8] = (uint8_t)(g_screen_on ? 1 : 0);
            sendto(g_udp_fd, ack, sizeof(ack), 0, (struct sockaddr *)&from, flen);
            continue;
        }

        if (memcmp(buf, "AGTI", 4) != 0 || n < 5) continue;
        uint8_t kind = buf[4];

        if (kind == 1 && n >= 11) { /* MOUSE: action(1), button(1), x(i16), y(i16) */
            uint8_t act = buf[5];
            uint8_t btn = buf[6];
            int16_t mx = (int16_t)(buf[7] | (buf[8] << 8));
            int16_t my = (int16_t)(buf[9] | (buf[10] << 8));
            if (mx < 0) mx = 0; if (mx >= g_xv_w) mx = (int16_t)(g_xv_w - 1);
            if (my < 0) my = 0; if (my >= g_xv_h) my = (int16_t)(g_xv_h - 1);
            pXTestMotion(dpy, -1, mx, my, 0);
            if (act == 1) pXTestBtn(dpy, btn, 1, 0);
            else if (act == 2) pXTestBtn(dpy, btn, 0, 0);
            else if (act == 3) { pXTestBtn(dpy, btn, 1, 0); pXTestBtn(dpy, btn, 0, 0); }
            pXFlush(dpy);
        } else if (kind == 2 && n >= 10) { /* KEY: mods(1), keysym(u32) */
            uint8_t mods = buf[5];
            uint32_t ks = (uint32_t)buf[6] | ((uint32_t)buf[7] << 8) | ((uint32_t)buf[8] << 16) | ((uint32_t)buf[9] << 24);
            unsigned int kc = pXKeysymToKeycode(dpy, (unsigned long)ks);
            if (kc) {
                if ((mods & 1) && kc_ctrl)  pXTestKey(dpy, kc_ctrl, 1, 0);
                if ((mods & 2) && kc_alt)   pXTestKey(dpy, kc_alt, 1, 0);
                if ((mods & 4) && kc_shift) pXTestKey(dpy, kc_shift, 1, 0);
                if ((mods & 8) && kc_meta)  pXTestKey(dpy, kc_meta, 1, 0);
                pXTestKey(dpy, kc, 1, 0);
                pXTestKey(dpy, kc, 0, 0);
                if ((mods & 8) && kc_meta)  pXTestKey(dpy, kc_meta, 0, 0);
                if ((mods & 4) && kc_shift) pXTestKey(dpy, kc_shift, 0, 0);
                if ((mods & 2) && kc_alt)   pXTestKey(dpy, kc_alt, 0, 0);
                if ((mods & 1) && kc_ctrl)  pXTestKey(dpy, kc_ctrl, 0, 0);
                pXFlush(dpy);
            }
        } else if (kind == 3 && n >= 7) { /* UTF-8 TEXT: len(u16) + bytes */
            uint16_t tlen = (uint16_t)(buf[5] | (buf[6] << 8));
            if (7 + tlen > n) tlen = (uint16_t)(n - 7);
            size_t i = 0;
            const uint8_t *tp = buf + 7;
            while (i < tlen) {
                uint32_t cp = 0;
                if (tp[i] < 0x80) { cp = tp[i++]; }
                else if ((tp[i] & 0xE0) == 0xC0 && i + 1 < tlen) {
                    cp = ((tp[i] & 0x1F) << 6) | (tp[i + 1] & 0x3F); i += 2;
                } else if ((tp[i] & 0xF0) == 0xE0 && i + 2 < tlen) {
                    cp = ((tp[i] & 0x0F) << 12) | ((tp[i + 1] & 0x3F) << 6) | (tp[i + 2] & 0x3F); i += 3;
                } else { i++; continue; }

                unsigned int kc = 0; int sh = 0;
                for (int k = 0; k < 12; k++) {
                    if (g_tr_cp[k].cp == cp) { kc = g_tr_cp[k].kc; sh = g_tr_cp[k].shift; break; }
                }
                if (!kc && cp < 128) {
                    char ch = (char)cp;
                    const char *sname = ascii_sym(ch, &sh);
                    if (sname) {
                        kc = pXKeysymToKeycode(dpy, pXStringToKeysym(sname));
                    } else {
                        char tmp[2] = { (ch >= 'A' && ch <= 'Z') ? (char)(ch + 32) : ch, 0 };
                        kc = pXKeysymToKeycode(dpy, pXStringToKeysym(tmp));
                    }
                }
                if (kc) {
                    if (sh && kc_shift) pXTestKey(dpy, kc_shift, 1, 0);
                    pXTestKey(dpy, kc, 1, 0);
                    pXTestKey(dpy, kc, 0, 0);
                    if (sh && kc_shift) pXTestKey(dpy, kc_shift, 0, 0);
                }
            }
            pXFlush(dpy);
        } else if (kind == 4 && n >= 6) { /* CMD */
            uint8_t cmd = buf[5];
            if (cmd == 4) {
                set_screen(!g_screen_on);
            } else if (cmd == 1) {
                char sc[512];
                snprintf(sc, sizeof(sc),
                    "su - ubuntu -c \"DISPLAY=:0 nohup /usr/bin/chromium --no-sandbox --test-type --disable-dev-shm-usage "
                    "--new-window --window-size=%d,%d --window-position=0,28 --user-data-dir=/home/ubuntu/.config/chr_xfce "
                    "https://www.google.com/ >/tmp/chr_xfce.log 2>&1 &\" &", g_xv_w, g_xv_h > 80 ? g_xv_h - 80 : 600);
                int r = system(sc); (void)r;
            } else if (cmd == 2) {
                int r = system("su - ubuntu -c \"DISPLAY=:0 nohup xfce4-terminal --geometry=120x32+80+60 >/tmp/term_xfce.log 2>&1 &\" &"); (void)r;
            } else if (cmd == 3) {
                int r = system("su - ubuntu -c \"DISPLAY=:0 nohup thunar /home/ubuntu >/tmp/thunar_xfce.log 2>&1 &\" &"); (void)r;
            } else if (cmd == 5) {
                int r = system("/usr/local/bin/ekran xfce yatay &"); (void)r;
            } else if (cmd == 6) {
                int r = system("/usr/local/bin/ekran xfce dikey &"); (void)r;
            }
        }
    }
    return NULL;
}

/* Blend XFixes ARGB cursor onto BGRX frame buffer */
static void overlay_cursor(uint32_t *buf, int w, int h, const my_XFixesCursorImage *ci) {
    if (!ci || !ci->pixels || ci->width == 0 || ci->height == 0) return;
    int ox = (int)ci->x - (int)ci->xhot;
    int oy = (int)ci->y - (int)ci->yhot;
    for (int cy = 0; cy < ci->height; cy++) {
        int dy = oy + cy;
        if (dy < 0 || dy >= h) continue;
        for (int cx = 0; cx < ci->width; cx++) {
            int dx = ox + cx;
            if (dx < 0 || dx >= w) continue;
            uint32_t c = (uint32_t)ci->pixels[cy * ci->width + cx];
            uint32_t a = (c >> 24) & 0xffU;
            if (a == 0) continue;
            uint32_t *dst = &buf[dy * w + dx];
            if (a == 255) {
                *dst = c;
            } else {
                uint32_t d = *dst;
                uint32_t ia = 255U - a;
                uint32_t cr = (c >> 16) & 0xffU, cg = (c >> 8) & 0xffU, cb = c & 0xffU;
                uint32_t dr = (d >> 16) & 0xffU, dg = (d >> 8) & 0xffU, db = d & 0xffU;
                uint32_t rr = (cr * a + dr * ia) / 255U;
                uint32_t rg = (cg * a + dg * ia) / 255U;
                uint32_t rb = (cb * a + db * ia) / 255U;
                *dst = (rr << 16) | (rg << 8) | rb;
            }
        }
    }
}

static void bgrx_to_yuyv_neon(const uint8_t *src, uint8_t *dst, int w, int h) {
    const uint8x8_t k66  = vdup_n_u8(66);
    const uint8x8_t k129 = vdup_n_u8(129);
    const uint8x8_t k25  = vdup_n_u8(25);
    const int16x8_t km38 = vdupq_n_s16(-38);
    const int16x8_t km74 = vdupq_n_s16(-74);
    const int16x8_t k112 = vdupq_n_s16(112);
    const int16x8_t km94 = vdupq_n_s16(-94);
    const int16x8_t km18 = vdupq_n_s16(-18);

    for (int y = 0; y < h; y++) {
        const uint8_t *s = src + (size_t)y * w * 4;
        uint8_t *d = dst + (size_t)y * w * 2;
        int x = 0;
        for (; x + 8 <= w; x += 8) {
            uint8x8x4_t bgrx = vld4_u8(s);
            uint16x8_t y16 = vmull_u8(bgrx.val[2], k66);
            y16 = vmlal_u8(y16, bgrx.val[1], k129);
            y16 = vmlal_u8(y16, bgrx.val[0], k25);
            y16 = vaddq_u16(y16, vdupq_n_u16(128));
            uint8x8_t Y = vadd_u8(vqshrn_n_u16(y16, 8), vdup_n_u8(16));

            int16x8_t r16 = vreinterpretq_s16_u16(vmovl_u8(bgrx.val[2]));
            int16x8_t g16 = vreinterpretq_s16_u16(vmovl_u8(bgrx.val[1]));
            int16x8_t b16 = vreinterpretq_s16_u16(vmovl_u8(bgrx.val[0]));

            int16x8_t u16 = vaddq_s16(vmulq_s16(r16, km38), vmulq_s16(g16, km74));
            u16 = vaddq_s16(u16, vmulq_s16(b16, k112));
            u16 = vaddq_s16(u16, vdupq_n_s16(128));
            uint8x8_t U = vqmovun_s16(vaddq_s16(vshrq_n_s16(u16, 8), vdupq_n_s16(128)));

            int16x8_t v16 = vaddq_s16(vmulq_s16(r16, k112), vmulq_s16(g16, km94));
            v16 = vaddq_s16(v16, vmulq_s16(b16, km18));
            v16 = vaddq_s16(v16, vdupq_n_s16(128));
            uint8x8_t V = vqmovun_s16(vaddq_s16(vshrq_n_s16(v16, 8), vdupq_n_s16(128)));

            uint8x8x2_t y_pairs = vtrn_u8(Y, Y);
            uint8x8_t y_even = y_pairs.val[0];
            uint8x8_t y_odd  = y_pairs.val[1];
            uint8x8x4_t out;
            out.val[0] = vuzp1_u8(y_even, y_even);
            out.val[1] = vuzp1_u8(U, U);
            out.val[2] = vuzp1_u8(y_odd, y_odd);
            out.val[3] = vuzp1_u8(V, V);
            uint8_t tmp[32];
            vst4_u8(tmp, out);
            memcpy(d, tmp, 16);
            s += 32; d += 16;
        }
        for (; x < w; x += 2) {
            int b0 = s[0], g0 = s[1], r0 = s[2];
            int b1 = s[4], g1 = s[5], r1 = s[6];
            int y0 = ((66 * r0 + 129 * g0 + 25 * b0 + 128) >> 8) + 16;
            int y1 = ((66 * r1 + 129 * g1 + 25 * b1 + 128) >> 8) + 16;
            int u  = ((-38 * r0 - 74 * g0 + 112 * b0 + 128) >> 8) + 128;
            int v  = ((112 * r0 - 94 * g0 - 18 * b0 + 128) >> 8) + 128;
            d[0] = (uint8_t)(y0 < 0 ? 0 : (y0 > 255 ? 255 : y0));
            d[1] = (uint8_t)(u < 0 ? 0 : (u > 255 ? 255 : u));
            d[2] = (uint8_t)(y1 < 0 ? 0 : (y1 > 255 ? 255 : y1));
            d[3] = (uint8_t)(v < 0 ? 0 : (v > 255 ? 255 : v));
            s += 8; d += 4;
        }
    }
}

typedef struct {
    int ion_fd, vfd;
    int in_h, in_fd, cap_h, cap_fd;
    uint8_t *in_map, *cap_map;
    size_t in_size, cap_size;
} hwjpeg_ctx;

static int ion_alloc_buf(int ion_fd, size_t sz, int *out_h, int *out_fd, uint8_t **out_map) {
    struct mtk_ion_alloc_data ad = { .len = sz, .align = 4096, .heap_id_mask = ION_HEAP_MULTIMEDIA_MASK, .flags = 0 };
    if (ioctl(ion_fd, ION_IOC_ALLOC, &ad) < 0) return -1;
    struct mtk_ion_fd_data fd_d = { .handle = ad.handle, .fd = -1 };
    if (ioctl(ion_fd, ION_IOC_SHARE, &fd_d) < 0) return -1;
    void *m = mmap(NULL, sz, PROT_READ | PROT_WRITE, MAP_SHARED, fd_d.fd, 0);
    if (m == MAP_FAILED) return -1;
    *out_h = ad.handle; *out_fd = fd_d.fd; *out_map = (uint8_t *)m;
    return 0;
}

static int hwjpeg_init(hwjpeg_ctx *c, int w, int h) {
    memset(c, 0, sizeof(*c));
    c->ion_fd = open("/dev/ion", O_RDWR);
    c->vfd = open("/dev/video4", O_RDWR);
    if (c->ion_fd < 0 || c->vfd < 0) return -1;

    struct v4l2_control ctrl = { .id = V4L2_CID_JPEG_COMPRESSION_QUALITY, .value = 88 };
    ioctl(c->vfd, VIDIOC_S_CTRL, &ctrl);

    struct v4l2_format f_out = {0};
    f_out.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
    f_out.fmt.pix_mp.width = w;
    f_out.fmt.pix_mp.height = h;
    f_out.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_YUYV;
    f_out.fmt.pix_mp.num_planes = 1;
    f_out.fmt.pix_mp.plane_fmt[0].bytesperline = w * 2;
    f_out.fmt.pix_mp.plane_fmt[0].sizeimage = (uint32_t)(w * h * 2);
    if (ioctl(c->vfd, VIDIOC_S_FMT, &f_out) < 0) return -2;
    c->in_size = f_out.fmt.pix_mp.plane_fmt[0].sizeimage ? f_out.fmt.pix_mp.plane_fmt[0].sizeimage : (size_t)w * h * 2;

    struct v4l2_format f_cap = {0};
    f_cap.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    f_cap.fmt.pix_mp.width = w;
    f_cap.fmt.pix_mp.height = h;
    f_cap.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_JPEG;
    f_cap.fmt.pix_mp.num_planes = 1;
    f_cap.fmt.pix_mp.plane_fmt[0].sizeimage = (uint32_t)(w * h * 2);
    if (ioctl(c->vfd, VIDIOC_S_FMT, &f_cap) < 0) return -3;
    c->cap_size = f_cap.fmt.pix_mp.plane_fmt[0].sizeimage ? f_cap.fmt.pix_mp.plane_fmt[0].sizeimage : (size_t)w * h * 2;

    if (ion_alloc_buf(c->ion_fd, c->in_size, &c->in_h, &c->in_fd, &c->in_map) < 0) return -4;
    if (ion_alloc_buf(c->ion_fd, c->cap_size, &c->cap_h, &c->cap_fd, &c->cap_map) < 0) return -5;

    struct v4l2_requestbuffers req_o = { .count = 1, .type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, .memory = V4L2_MEMORY_DMABUF };
    struct v4l2_requestbuffers req_c = { .count = 1, .type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE, .memory = V4L2_MEMORY_DMABUF };
    if (ioctl(c->vfd, VIDIOC_REQBUFS, &req_o) < 0) return -6;
    if (ioctl(c->vfd, VIDIOC_REQBUFS, &req_c) < 0) return -7;

    int t_o = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, t_c = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    if (ioctl(c->vfd, VIDIOC_STREAMON, &t_o) < 0) return -8;
    if (ioctl(c->vfd, VIDIOC_STREAMON, &t_c) < 0) return -9;
    return 0;
}

static ssize_t hwjpeg_encode(hwjpeg_ctx *c, const uint32_t *bgrx, int w, int h) {
    bgrx_to_yuyv_neon((const uint8_t *)bgrx, c->in_map, w, h);

    struct v4l2_plane po = {0}, pc = {0};
    po.m.fd = c->in_fd; po.length = (uint32_t)c->in_size; po.bytesused = (uint32_t)(w * h * 2);
    pc.m.fd = c->cap_fd; pc.length = (uint32_t)c->cap_size;

    struct v4l2_buffer bo = {0}, bc = {0};
    bo.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE; bo.memory = V4L2_MEMORY_DMABUF; bo.index = 0; bo.length = 1; bo.m.planes = &po;
    bc.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE; bc.memory = V4L2_MEMORY_DMABUF; bc.index = 0; bc.length = 1; bc.m.planes = &pc;

    if (ioctl(c->vfd, VIDIOC_QBUF, &bc) < 0) return -1;
    if (ioctl(c->vfd, VIDIOC_QBUF, &bo) < 0) return -2;

    if (ioctl(c->vfd, VIDIOC_DQBUF, &bc) < 0) return -3;
    if (ioctl(c->vfd, VIDIOC_DQBUF, &bo) < 0) return -4;
    return (ssize_t)bc.m.planes[0].bytesused;
}

static void *accept_thread(void *arg) {
    (void)arg;
    unlink(XFCE_SOCK);
    g_srv_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un sa = {0};
    sa.sun_family = AF_UNIX;
    strncpy(sa.sun_path, XFCE_SOCK, sizeof(sa.sun_path) - 1);
    if (bind(g_srv_fd, (struct sockaddr *)&sa, sizeof(sa)) < 0) return NULL;
    chmod(XFCE_SOCK, 0666);
    listen(g_srv_fd, 4);

    while (g_running) {
        int cfd = accept(g_srv_fd, NULL, NULL);
        if (cfd < 0) { usleep(100000); continue; }
        pthread_mutex_lock(&g_cli_mu);
        if (g_cli_fd >= 0) close(g_cli_fd);
        g_cli_fd = cfd;
        g_force_frame = 1;
        pthread_mutex_unlock(&g_cli_mu);
    }
    return NULL;
}

static void send_frame(const uint8_t *jpg, uint32_t len) {
    int fd_shm = open(XFCE_SHM_JPG ".tmp", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd_shm >= 0) {
        ssize_t w = write(fd_shm, jpg, len);
        (void)w;
        close(fd_shm);
        rename(XFCE_SHM_JPG ".tmp", XFCE_SHM_JPG);
    }

    pthread_mutex_lock(&g_cli_mu);
    if (g_cli_fd >= 0) {
        uint8_t hdr[4] = { len & 0xff, (len >> 8) & 0xff, (len >> 16) & 0xff, (len >> 24) & 0xff };
        if (send(g_cli_fd, hdr, 4, MSG_NOSIGNAL) != 4 ||
            send(g_cli_fd, jpg, len, MSG_NOSIGNAL) != (ssize_t)len) {
            close(g_cli_fd);
            g_cli_fd = -1;
        }
    }
    pthread_mutex_unlock(&g_cli_mu);

    /* Direct zero-broker UDP chunked frame blast */
    pthread_mutex_lock(&g_udp_mu);
    int has_u = (g_udp_has_cli && g_udp_fd >= 0 && (now_ms() - g_udp_last_hello_ms <= 10000));
    struct sockaddr_in ucli = g_udp_cli;
    if (!has_u) g_udp_has_cli = 0;
    pthread_mutex_unlock(&g_udp_mu);

    if (has_u) {
        uint32_t fid = ++g_udp_frame_id;
        uint16_t cnt = (uint16_t)((len + UDP_CHUNK_PAYLOAD - 1) / UDP_CHUNK_PAYLOAD);
        uint8_t pkt[sizeof(udp_chunk_hdr_t) + UDP_CHUNK_PAYLOAD];
        for (uint16_t idx = 0; idx < cnt; idx++) {
            uint32_t off = (uint32_t)idx * UDP_CHUNK_PAYLOAD;
            uint32_t plen = len - off;
            if (plen > UDP_CHUNK_PAYLOAD) plen = UDP_CHUNK_PAYLOAD;
            udp_chunk_hdr_t *h = (udp_chunk_hdr_t *)pkt;
            memcpy(h->magic, "AGTU", 4);
            h->frame_id = fid;
            h->total_size = len;
            h->chunk_idx = idx;
            h->chunk_cnt = cnt;
            memcpy(pkt + sizeof(*h), jpg + off, plen);
            sendto(g_udp_fd, pkt, sizeof(*h) + plen, 0, (struct sockaddr *)&ucli, sizeof(ucli));
        }
    }
}

static void *enc_thread(void *arg) {
    (void)arg;
    hwjpeg_ctx ctx;
    if (hwjpeg_init(&ctx, g_xv_w, g_xv_h) < 0) {
        fprintf(stderr, "fb_xfce_bridge: /dev/video4 hwjpeg_init failed\n");
        return NULL;
    }
    uint32_t *local = malloc((size_t)g_xv_w * g_xv_h * 4);
    while (g_running) {
        pthread_mutex_lock(&g_enc_mu);
        while (g_running && !g_enc_ready) pthread_cond_wait(&g_enc_cv, &g_enc_mu);
        if (!g_running) { pthread_mutex_unlock(&g_enc_mu); break; }
        memcpy(local, g_enc_buf, (size_t)g_xv_w * g_xv_h * 4);
        g_enc_ready = 0;
        pthread_mutex_unlock(&g_enc_mu);

        ssize_t jsz = hwjpeg_encode(&ctx, local, g_xv_w, g_xv_h);
        if (jsz > 0) send_frame(ctx.cap_map, (uint32_t)jsz);
    }
    free(local);
    return NULL;
}

static void on_sig(int s) { (void)s; g_running = 0; pthread_cond_broadcast(&g_enc_cv); }

static uint32_t read_be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

int main(int argc, char **argv) {
    const char *disp = argc > 1 ? argv[1] : ":0";
    signal(SIGTERM, on_sig);
    signal(SIGINT, on_sig);
    signal(SIGPIPE, SIG_IGN);

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
    g_xv_w = (int)read_be32(xmap + 16);
    g_xv_h = (int)read_be32(xmap + 20);
    uint32_t ncolors = read_be32(xmap + 76);
    g_landscape = (g_xv_w == FB_H && g_xv_h == FB_W) ? 1 : 0;

    size_t pix_off = hdr_sz + ncolors * 12;
    const uint32_t *src = (const uint32_t *)(xmap + pix_off);

    int fbfd = open("/dev/fb0", O_RDWR);
    if (fbfd < 0) { perror("open /dev/fb0"); return 3; }

    size_t fb_bytes = (size_t)FB_STRIDE_PX * FB_H * 4;
    uint32_t *fb_map = mmap(NULL, fb_bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fbfd, 0);
    uint32_t *prev_raw = calloc((size_t)FB_W * FB_H, 4);
    uint32_t *composed = malloc((size_t)g_xv_w * g_xv_h * 4);
    g_enc_buf = malloc((size_t)g_xv_w * g_xv_h * 4);

    struct fb_var_screeninfo vinfo;
    ioctl(fbfd, FBIOGET_VSCREENINFO, &vinfo);

    /* Open UDP port 9900 with large kernel buffers */
    g_udp_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (g_udp_fd >= 0) {
        int sb = 4 * 1024 * 1024, rb = 1 * 1024 * 1024;
        setsockopt(g_udp_fd, SOL_SOCKET, SO_SNDBUF, &sb, sizeof(sb));
        setsockopt(g_udp_fd, SOL_SOCKET, SO_RCVBUF, &rb, sizeof(rb));
        struct sockaddr_in bind_addr = {0};
        bind_addr.sin_family = AF_INET;
        bind_addr.sin_addr.s_addr = INADDR_ANY;
        bind_addr.sin_port = htons(UDP_PORT);
        if (bind(g_udp_fd, (struct sockaddr *)&bind_addr, sizeof(bind_addr)) < 0) {
            perror("bind udp 9900");
            close(g_udp_fd);
            g_udp_fd = -1;
        }
    }

    /* Load X11 + XFixes to read real cursor shape & position */
    void *hx11 = dlopen("libX11.so.6", RTLD_NOW | RTLD_GLOBAL);
    int (*pXInitThreads)(void) = hx11 ? dlsym(hx11, "XInitThreads") : NULL;
    if (pXInitThreads) pXInitThreads();
    void *hxfix = dlopen("libXfixes.so.3", RTLD_NOW);
    void *(*pXOpenDisplay)(const char *) = hx11 ? dlsym(hx11, "XOpenDisplay") : NULL;
    int (*pXFree)(void *) = hx11 ? dlsym(hx11, "XFree") : NULL;
    my_XFixesCursorImage *(*pGetCursor)(void *) = hxfix ? dlsym(hxfix, "XFixesGetCursorImage") : NULL;
    void *cur_dpy = pXOpenDisplay ? pXOpenDisplay(disp) : NULL;

    set_screen(1);

    pthread_t th_pwr, th_fifo, th_tch, th_acc, th_enc, th_urx;
    pthread_create(&th_pwr, NULL, power_thread, NULL);
    pthread_create(&th_fifo, NULL, fifo_thread, NULL);
    pthread_create(&th_tch, NULL, touch_thread, (void *)disp);
    pthread_create(&th_acc, NULL, accept_thread, NULL);
    pthread_create(&th_enc, NULL, enc_thread, NULL);
    if (g_udp_fd >= 0) pthread_create(&th_urx, NULL, udp_rx_thread, (void *)disp);

    uint64_t last_enc_ms = 0;
    int prev_cx = -999, prev_cy = -999;
    unsigned long prev_serial = 0;

    while (g_running) {
        uint64_t t = now_ms();
        int has_cli = (g_cli_fd >= 0 || (g_udp_has_cli && t - g_udp_last_hello_ms <= 10000));
        int fb_changed = (memcmp(src, prev_raw, (size_t)FB_W * FB_H * 4) != 0);
        my_XFixesCursorImage *ci = (cur_dpy && pGetCursor) ? pGetCursor(cur_dpy) : NULL;
        int cur_changed = (ci && (ci->x != prev_cx || ci->y != prev_cy || ci->cursor_serial != prev_serial));
        int need_hb = (g_force_frame || (has_cli && t - last_enc_ms >= 500));

        if (fb_changed || cur_changed || need_hb) {
            if (fb_changed) memcpy(prev_raw, src, (size_t)FB_W * FB_H * 4);
            if (ci) { prev_cx = ci->x; prev_cy = ci->y; prev_serial = ci->cursor_serial; }

            memcpy(composed, prev_raw, (size_t)g_xv_w * g_xv_h * 4);
            if (ci) overlay_cursor(composed, g_xv_w, g_xv_h, ci);

            if ((fb_changed || cur_changed) && g_screen_on && fb_map != MAP_FAILED) {
                if (!g_landscape) {
                    for (int y = 0; y < FB_H; y++) {
                        const uint32_t *srow = composed + y * FB_W;
                        uint32_t *drow = fb_map + y * FB_STRIDE_PX;
                        for (int x = 0; x < FB_W; x++) {
                            uint32_t p = srow[x];
                            drow[x] = (p & 0x0000FF00U) | ((p & 0xFFU) << 16) | ((p >> 16) & 0xFFU) | 0xFF000000U;
                        }
                    }
                } else {
                    for (int y_fb = 0; y_fb < FB_H; y_fb++) {
                        int vx = (FB_H - 1) - y_fb;
                        uint32_t *drow = fb_map + y_fb * FB_STRIDE_PX;
                        const uint32_t *scol = composed + vx;
                        for (int x_fb = 0; x_fb < FB_W; x_fb++) {
                            uint32_t p = scol[x_fb * FB_H];
                            drow[x_fb] = (p & 0x0000FF00U) | ((p & 0xFFU) << 16) | ((p >> 16) & 0xFFU) | 0xFF000000U;
                        }
                    }
                }
                vinfo.xoffset = 0; vinfo.yoffset = 0;
                ioctl(fbfd, FBIOPAN_DISPLAY, &vinfo);
            }

            if (need_hb || (has_cli && t - last_enc_ms >= 22) || (t - last_enc_ms >= 400)) {
                g_force_frame = 0;
                last_enc_ms = t;
                pthread_mutex_lock(&g_enc_mu);
                memcpy(g_enc_buf, composed, (size_t)g_xv_w * g_xv_h * 4);
                g_enc_ready = 1;
                pthread_cond_signal(&g_enc_cv);
                pthread_mutex_unlock(&g_enc_mu);
            }
        }
        if (ci && pXFree) pXFree(ci);
        usleep(16000);
    }

    set_screen(0);
    if (g_udp_fd >= 0) close(g_udp_fd);
    if (g_srv_fd >= 0) close(g_srv_fd);
    unlink(XFCE_SOCK);
    free(prev_raw);
    free(composed);
    free(g_enc_buf);
    munmap(xmap, st.st_size);
    if (fb_map != MAP_FAILED) munmap(fb_map, fb_bytes);
    close(fbfd);
    close(xfd);
    return 0;
}

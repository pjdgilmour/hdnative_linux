/* 1 kHz at 48 kHz, peak -40 dBFS, generated from signed 24-bit full scale.
 * DirectIO RVA fbe2..fc77: 256-byte frame, first two samples at +4 and +7.
 * Pure helper shared by kernel probe and userspace golden-vector tests.
 */
#ifndef AVID_NATIVE_TONE_H
#define AVID_NATIVE_TONE_H
static const int native_tone_48[48] = {
    0, 10949, 21711, 32102, 41943, 51067, 59316, 66551,
    72647, 77501, 81028, 83168, 83886, 83168, 81028, 77501,
    72647, 66551, 59316, 51067, 41943, 32102, 21711, 10949,
    0, -10949, -21711, -32102, -41943, -51067, -59316, -66551,
    -72647, -77501, -81028, -83168, -83886, -83168, -81028, -77501,
    -72647, -66551, -59316, -51067, -41943, -32102, -21711, -10949,
};
static void native_fill_tone(unsigned char *buffer, int longer)
{
    unsigned int i, ch;
    unsigned int frames = longer ? 6144 : 1024;
    for (i = 0; i < frames; i++) {
        unsigned int ramp = i < 128 ? i : i >= frames - 128 ? frames - 1 - i : 128;
        int sample = native_tone_48[i % 48] * (int)ramp / 128;
        unsigned int bits = (unsigned int)sample & 0xffffff;
        for (ch = 0; ch < 2; ch++) {
            unsigned char *p = buffer + i * 256 + 4 + ch * 3;
            p[0] = bits & 255;
            p[1] = (bits >> 8) & 255;
            p[2] = (bits >> 16) & 255;
        }
    }
}
#endif

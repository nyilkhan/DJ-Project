// app/ui/qml/shaders/waveform.frag
#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(binding = 1) uniform sampler2D waveTex;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;

    vec4 waveColor;
    vec4 bgColor;

    // viewport playhead (0..1). For scrolling view, keep this at 0.5.
    float playhead;
    float playheadWidth;

    // scrolling window over the full-track texture (0..1)
    float zoomStart;   // left edge of visible window in the full track
    float zoomWidth;   // width of visible window in the full track

    // cosmetics
    float centerLineWidth; // thickness of the center horizontal line in uv-space
};

void main() {
    vec2 uv = qt_TexCoord0;

    // Map viewport x to global track x (scrolling window)
    float globalX = zoomStart + uv.x * zoomWidth;
    globalX = clamp(globalX, 0.0, 1.0);

    // waveTex is 1px-high: R=min, G=max in 0..1
    vec4 mm = texture(waveTex, vec2(globalX, 0.5));
    float mn = mm.r * 2.0 - 1.0;  // back to -1..1
    float mx = mm.g * 2.0 - 1.0;

    // Convert y from 0..1 to -1..1 centered waveform space
    float y = uv.y * 2.0 - 1.0;

    float lo = min(mn, mx);
    float hi = max(mn, mx);

    bool inWave = (y >= lo) && (y <= hi);

    // Optional center line
    bool inCenter = abs(uv.y - 0.5) < centerLineWidth;

    // Playhead in VIEWPORT coordinates
    bool inPlayhead = abs(uv.x - playhead) < playheadWidth;

    vec4 c = bgColor;

    if (inCenter) c = mix(bgColor, vec4(1.0, 1.0, 1.0, 1.0), 0.10);
    if (inWave)   c = waveColor;
    if (inPlayhead) c = vec4(1.0, 1.0, 0.0, 1.0);

    fragColor = c * qt_Opacity;
}

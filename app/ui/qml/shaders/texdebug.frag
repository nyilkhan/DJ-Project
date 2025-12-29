#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(binding = 1) uniform sampler2D waveTex;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
};

void main() {
    fragColor = texture(waveTex, vec2(qt_TexCoord0.x, 0.5)) * qt_Opacity;
}

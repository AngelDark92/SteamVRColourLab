"""Actual application shaders, also compiled and exercised by the GL tests."""
VERTEX = r'''#version 330 core
uniform mat4 u_mvp;
out vec2 v_uv;
void main() {
    // Two triangles; analytic UVs avoid source images and texture interpolation.
    vec2 p[6] = vec2[](vec2(-1,-1),vec2(1,-1),vec2(1,1),
                      vec2(-1,-1),vec2(1,1),vec2(-1,1));
    vec2 xy = p[gl_VertexID];
    v_uv = xy * 0.5 + 0.5;
    gl_Position = u_mvp * vec4(xy, 0.0, 1.0);
}
'''

FRAGMENT = r'''#version 330 core
in vec2 v_uv;
out vec4 frag;
uniform vec3 u_start;
uniform vec3 u_end;
uniform int u_mode;       // 0=8, 1=10, 2=reference, 3=compare, 4=three, 5=dither8
uniform int u_pattern;    // horizontal, vertical, radial, solid, hue, atlas
uniform int u_labels;
uniform int u_swap;
uniform float u_seconds; // zero for the static test
uniform float u_hue;
uniform float u_sat;
uniform float u_low;
uniform float u_high;

vec3 toLinear(vec3 s) {
    vec3 lo = s / 12.92;
    vec3 hi = pow((s + 0.055) / 1.055, vec3(2.4));
    return mix(hi, lo, lessThanEqual(s, vec3(0.04045)));
}
vec3 hsv(float h, float s, float v) {
    vec3 p = abs(fract(vec3(h) + vec3(0.0, 2.0/3.0, 1.0/3.0))*6.0-3.0);
    return v * mix(vec3(1.0), clamp(p-1.0,0.0,1.0), s);
}
uint hash(uint x) {
    x ^= x >> 16u; x *= 0x7feb352du;
    x ^= x >> 15u; x *= 0x846ca68bu;
    x ^= x >> 16u; return x;
}
float noise(uvec2 p, uint seed) {
    // The 24-bit result converts exactly to float; fixed in panel UV space.
    return float(hash(p.x ^ hash(p.y + seed)) & 0x00ffffffu) / 16777216.0 - 0.5;
}
// Original tiny 5x7 glyphs, represented as five column masks (bottom bit first).
int glyph(int ch, int x) {
    if (x < 0 || x > 4) return 0;
    if (ch == 8) { int a[5]=int[](54,73,73,73,54); return a[x]; }
    if (ch == 1) { int a[5]=int[](0,33,127,1,0); return a[x]; }
    if (ch == 0) { int a[5]=int[](62,65,65,65,62); return a[x]; }
    if (ch == 2) { int a[5]=int[](127,72,76,74,49); return a[x]; } // R
    if (ch == 3) { int a[5]=int[](127,73,73,73,65); return a[x]; } // E
    if (ch == 4) { int a[5]=int[](127,72,72,72,64); return a[x]; } // F
    return 0;
}
bool labelPixel(vec2 uv, int kind) {
    ivec2 p = ivec2(floor((uv - vec2(0.014,0.906))*vec2(500.0,140.0)));
    if (p.x < 0 || p.y < 0 || p.y > 6) return false;
    int idx = p.x/6; int ch = -1;
    if (kind == 0 || kind == 5) { if (idx == 0) ch=8; }
    else if (kind == 1) { if (idx==0) ch=1; if (idx==1) ch=0; }
    else { if (idx==0) ch=2; if (idx==1) ch=3; if (idx==2) ch=4; }
    return ((glyph(ch,p.x%6) >> p.y)&1) != 0;
}
void main() {
    vec2 uv = v_uv;
    float atlasHue = 0.0;
    if (u_pattern == 5) {
        vec2 cell = floor(min(uv, vec2(0.999999)) * vec2(4,3));
        atlasHue = (cell.x + (2.0-cell.y)*4.0)/12.0 + u_hue;
        uv = fract(uv * vec2(4,3));
        if (uv.x < 0.012 || uv.y < 0.016) { frag=vec4(0,0,0,1); return; }
        uv = clamp((uv-vec2(0.012,0.016))/vec2(0.988,0.984),0.0,1.0);
    }
    int kind = u_mode;
    if (u_mode == 3 || u_mode == 4) {
        int count = (u_mode == 3) ? 2 : 3;
        // Top-to-bottom ordering. Every section has the same local ramp domain.
        int topIndex = min(count-1, int((1.0-uv.y)*float(count)));
        kind = (u_swap == 1) ? count-1-topIndex : topIndex;
        uv.y = clamp(uv.y*float(count)-float(count-1-topIndex),0.0,1.0);
    }
    if (u_labels == 1 && uv.y > 0.88) {
        frag = vec4(labelPixel(uv,kind) ? vec3(0.6) : vec3(0.006),1.0);
        return;
    }
    if (u_labels == 1) uv.y = clamp(uv.y/0.88,0.0,1.0);
    float t = uv.x;
    if (u_pattern == 1) t = uv.y;
    if (u_pattern == 2) t = clamp(length((uv-0.5)*2.0),0.0,1.0);
    if (u_pattern == 3) t = 0.0;
    if (u_seconds > 0.0 && u_pattern != 3)
        t = 1.0-abs(2.0*fract(t*0.5 + u_seconds*0.03)-1.0);
    vec3 s = mix(u_start,u_end,t);
    if (u_pattern == 4) s = hsv(t+u_hue,u_sat,u_high);
    if (u_pattern == 5) s = hsv(atlasHue,u_sat,mix(u_low,u_high,t));
    s = clamp(s,0.0,1.0);
    if (kind == 0 || kind == 1 || kind == 5) {
        float levels = (kind == 1) ? 1023.0 : 255.0;
        vec3 d = vec3(0.0);
        if (kind == 5) {
            uvec2 p = uvec2(floor(uv * vec2(2048,2048)));
            d = vec3(noise(p,17u),noise(p,137u),noise(p,997u));
        }
        // Quantise *encoded* sRGB, then decode into the linear float eye buffer.
        s = clamp(floor(s*levels + d + 0.5)/levels,0.0,1.0);
    }
    frag = vec4(toLinear(s),1.0);
}
'''

PREVIEW_VERTEX = r'''#version 330 core
out vec2 v_uv;
void main() {
    vec2 p[3] = vec2[](vec2(-1,-1),vec2(3,-1),vec2(-1,3));
    gl_Position=vec4(p[gl_VertexID],0,1);
    v_uv=p[gl_VertexID]*0.5+0.5;
}
'''
PREVIEW_FRAGMENT = r'''#version 330 core
in vec2 v_uv;
out vec4 frag;
uniform sampler2D u_texture;
void main() {
    vec3 x=max(texture(u_texture,v_uv).rgb,vec3(0.0));
    vec3 s=mix(1.055*pow(x,vec3(1.0/2.4))-0.055,x*12.92,
               lessThanEqual(x,vec3(0.0031308)));
    frag=vec4(s,1.0);
}
'''

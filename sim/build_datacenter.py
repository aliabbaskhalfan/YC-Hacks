"""Generates scene_datacenter.xml (a server aisle) and go2_thermal.xml (Go2 with a thermal camera pod)."""
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "third_party" / "mujoco_menagerie" / "unitree_go2"
rng = random.Random(7)

W = 0.75             # half-width of the clear aisle (1.5 m cold aisle)
D = 1.07             # rack depth
H = 2.05             # rack height
RW = 0.6             # rack width along the aisle
X0, NR = -3.0, 32    # first rack edge, racks per row
X1 = X0 + NR * RW
CEIL = 3.3

CABLE = {"teal": "0.05 0.72 0.78 1", "yellow": "0.95 0.82 0.1 1",
         "purple": "0.5 0.32 0.9 1", "magenta": "0.85 0.2 0.45 1", "blue": "0.15 0.4 0.95 1"}

g = []
def geom(name, type_, size, pos, mat=None, rgba=None, collide=False, extra=""):
    attrs = f'name="{name}" type="{type_}" size="{size}" pos="{pos}"'
    attrs += f' material="{mat}"' if mat else f' rgba="{rgba}"'
    if not collide:
        attrs += ' contype="0" conaffinity="0"'
    g.append(f"    <geom {attrs} {extra}/>")

def f(*v):
    return " ".join(f"{x:.4f}" for x in v)

for side in (1, -1):
    tag = "L" if side > 0 else "R"
    yf = side * W                   # front face of the row
    yb = side * (W + D)             # back of the row
    for k in range(NR):
        xc = X0 + RW * (k + 0.5)
        n = f"{tag}{k:02d}"
        cable = rng.choice(list(CABLE))
        hot = side < 0 and k == 10   # the rack the robot should be inspecting when it fails

        # cabinet shell
        geom(f"{n}_back", "box", f(RW / 2, 0.01, H / 2), f(xc, yb, H / 2), "rack_black")
        geom(f"{n}_side", "box", f(0.008, D / 2, H / 2), f(xc - RW / 2 + 0.008, side * (W + D / 2), H / 2), "rack_black")
        geom(f"{n}_top", "box", f(RW / 2, D / 2, 0.03), f(xc, side * (W + D / 2), H + 0.03), "rack_black")
        geom(f"{n}_plinth", "box", f(RW / 2, D / 2, 0.05), f(xc, side * (W + D / 2), 0.05), "rack_black")

        # vertical cable managers either side of the door, with a coloured bundle inside one
        for j, dx in enumerate((-RW / 2 + 0.035, RW / 2 - 0.035)):
            geom(f"{n}_post{j}", "box", f(0.035, 0.03, H / 2), f(xc + dx, yf + side * 0.03, H / 2), "rack_frame")
        geom(f"{n}_bundle", "box", f(0.011, 0.012, H / 2 - 0.12), f(xc - 0.212, yf + side * 0.08, H / 2), cable)

        # servers: 1U-4U slabs with a vent strip, status LEDs and thin patch cable runs
        z = 0.14
        u = 0
        while z < H - 0.12:
            h = rng.choice((0.045, 0.09, 0.09, 0.13, 0.18))
            if z + h > H - 0.08:
                break
            geom(f"{n}_srv{u}", "box", f(0.215, 0.4, h / 2 - 0.003), f(xc + 0.02, yf + side * 0.5, z + h / 2), "server")
            yface = yf + side * 0.098
            geom(f"{n}_vent{u}", "box", f(0.09, 0.002, h / 2 - 0.012), f(xc - 0.07, yface, z + h / 2), "vent")
            led = "led_amber" if hot and rng.random() < 0.7 else rng.choice(("led_green", "led_green", "led_blue"))
            geom(f"{n}_led{u}", "box", f(0.005, 0.002, 0.003), f(xc + 0.2, yface, z + h / 2), led)
            if rng.random() < 0.7:
                c = cable if rng.random() < 0.8 else rng.choice(list(CABLE))
                for w in range(4):
                    half = rng.uniform(0.07, 0.12)
                    geom(f"{n}_patch{u}_{w}", "box", f(half, 0.004, 0.003),
                         f(xc + 0.2 - half - rng.uniform(0, 0.05), yface - side * 0.012, z + 0.012 + 0.009 * w), c)
            z += h
            u += 1

        if hot:
            geom(f"{n}_heat", "box", f(RW / 2 - 0.1, 0.004, 0.25), f(xc + 0.02, yf + side * 0.1, 1.3), "heat_glow")

        # glass door is the only part the robot collides with
        geom(f"{n}_glass", "box", f(RW / 2 - 0.07, 0.004, H / 2 - 0.05), f(xc, yf + side * 0.004, H / 2 + 0.03),
             "glass", collide=True)

    # overhead ladder tray with blue cable, and a yellow fibre raceway behind it
    L = (X1 - X0) / 2
    xm = (X0 + X1) / 2
    yt = side * (W + 0.35)
    for j, dy in enumerate((-0.2, 0.2)):
        geom(f"{tag}_tray_rail{j}", "box", f(L, 0.01, 0.03), f(xm, yt + dy, 2.5), "tray_black")
    geom(f"{tag}_tray_cable", "box", f(L, 0.17, 0.025), f(xm, yt, 2.49), "cable_blue")
    for r in range(int(2 * L / 0.3)):
        geom(f"{tag}_rung{r}", "box", f(0.012, 0.2, 0.008), f(X0 + 0.15 + 0.3 * r, yt, 2.465), "tray_black")
    geom(f"{tag}_fibre", "box", f(L, 0.09, 0.05), f(xm, side * (W + 0.85), 2.75), "fibre_yellow")
    for r in range(int(2 * L / 2.4) + 1):
        x = X0 + 2.4 * r
        for dy in (-0.2, 0.2):
            geom(f"{tag}_hanger{r}_{dy}", "cylinder", f(0.008, (CEIL - 2.5) / 2), f(x, yt + dy, (CEIL + 2.5) / 2), "tray_black")

    # wall behind the row (the next hot aisle is out of view)
    geom(f"{tag}_wall", "box", f(L + 2, 0.05, CEIL / 2), f(xm, side * (W + D + 1.0), CEIL / 2), "wall")

xm, L = (X0 + X1) / 2, (X1 - X0) / 2
geom("ceiling", "box", f(L + 2, W + D + 1.1, 0.05), f(xm, 0, CEIL + 0.05), "ceiling")
geom("wall_far", "box", f(0.05, W + D + 1.1, CEIL / 2), f(X1 + 1.5, 0, CEIL / 2), "wall")
geom("door_far", "box", f(0.02, 0.6, 1.05), f(X1 + 1.44, 0, 1.05), "door")
geom("exit_sign", "box", f(0.01, 0.2, 0.07), f(X1 + 1.43, 0, 2.35), "exit_green")
geom("wall_near", "box", f(0.05, W + D + 1.1, CEIL / 2), f(X0 - 1.5, 0, CEIL / 2), "wall")

# low-profile tool case left in the aisle, under the front left foot's path (foot lands at x~1.98, y~0.1)
TBX, TBY, TBH = 1.99, 0.11, 0.02
geom("toolbox", "box", f(0.15, 0.10, TBH), f(TBX, TBY, TBH), "toolbox_red", collide=True, extra='friction="1.0"')
geom("toolbox_seam", "box", f(0.152, 0.102, 0.002), f(TBX, TBY, TBH * 1.3), "toolbox_dark")
geom("toolbox_handle", "box", f(0.06, 0.008, 0.006), f(TBX, TBY - 0.103, TBH * 1.2), "toolbox_dark")
for j, dx in enumerate((-0.1, 0.1)):
    geom(f"toolbox_latch{j}", "box", f(0.012, 0.004, 0.008), f(TBX + dx, TBY - 0.102, TBH * 1.1), "chrome")

lights = []
for r in range(int(2 * L / 2.4) + 1):
    x = X0 + 1.2 + 2.4 * r
    geom(f"lightstrip{r}", "box", f(0.8, 0.07, 0.015), f(x, 0, CEIL - 0.02), "light_panel")
    # Non-shadow spotlights render surfaces above them black in MuJoCo 3.14, so only the shadow light is a spot.
    if r == 2:
        lights.append(f'    <light pos="{f(x, 0, CEIL - 0.1)}" dir="0 0 -1" diffuse="0.45 0.46 0.48" '
                      f'specular="0.15 0.15 0.15" attenuation="1 0.02 0.01" castshadow="true"/>')
    elif r % 2 == 0:
        lights.append(f'    <light type="directional" pos="{f(x, 0, CEIL - 0.1)}" dir="0 0.15 -1" diffuse="0.1 0.1 0.11" '
                      f'specular="0.05 0.05 0.05" castshadow="false"/>')

scene = f"""<mujoco model="go2 data center">
  <include file="go2_thermal.xml"/>

  <visual>
    <headlight diffuse="0.3 0.3 0.32" ambient="0.38 0.38 0.4" specular="0 0 0"/>
    <rgba haze="0.2 0.2 0.22 1"/>
    <global azimuth="0" elevation="-12" offwidth="1920" offheight="1080"/>
    <quality shadowsize="4096"/>
  </visual>

  <asset>
    <texture type="skybox" builtin="flat" rgb1="0.2 0.2 0.22" rgb2="0.2 0.2 0.22" width="32" height="32"/>
    <texture type="2d" name="tiles" builtin="checker" mark="edge" rgb1="0.87 0.88 0.89" rgb2="0.85 0.86 0.87"
      markrgb="0.7 0.71 0.73" width="512" height="512"/>
    <material name="floor" texture="tiles" texuniform="true" texrepeat="3.333 3.333" reflectance="0.12" shininess="0.6" specular="0.4"/>
    <material name="rack_black" rgba="0.035 0.035 0.04 1" specular="0.3" shininess="0.5"/>
    <material name="rack_frame" rgba="0.06 0.06 0.07 1" specular="0.7" shininess="0.9"/>
    <material name="server" rgba="0.15 0.15 0.16 1" specular="0.4" shininess="0.5"/>
    <material name="vent" rgba="0.24 0.24 0.26 1" specular="0.3"/>
    <material name="glass" rgba="0.55 0.7 0.8 0.12" specular="0.9" shininess="1"/>
    <material name="led_green" rgba="0.2 1 0.35 1" emission="1"/>
    <material name="led_blue" rgba="0.25 0.55 1 1" emission="1"/>
    <material name="led_amber" rgba="1 0.55 0.1 1" emission="1"/>
    <material name="heat_glow" rgba="1 0.35 0.1 0.18" emission="0.6"/>
{chr(10).join(f'    <material name="{k}" rgba="{v}" specular="0.2" emission="0.08"/>' for k, v in CABLE.items())}
    <material name="cable_blue" rgba="0.12 0.3 0.8 1" specular="0.2"/>
    <material name="tray_black" rgba="0.08 0.08 0.09 1" specular="0.4"/>
    <material name="fibre_yellow" rgba="0.95 0.8 0.1 1" specular="0.3"/>
    <material name="wall" rgba="0.72 0.73 0.75 1" emission="0.15"/>
    <material name="ceiling" rgba="0.8 0.81 0.83 1" emission="0.45"/>
    <material name="door" rgba="0.5 0.52 0.55 1"/>
    <material name="toolbox_red" rgba="0.8 0.1 0.07 1" specular="0.6" shininess="0.7"/>
    <material name="toolbox_dark" rgba="0.08 0.08 0.08 1"/>
    <material name="chrome" rgba="0.75 0.76 0.78 1" specular="1" shininess="1" reflectance="0.2"/>
    <material name="exit_green" rgba="0.1 0.9 0.3 1" emission="1"/>
    <material name="light_panel" rgba="1 1 1 1" emission="1"/>
  </asset>

  <worldbody>
{chr(10).join(lights)}
    <geom name="floor" size="0 0 0.05" type="plane" material="floor"/>
{chr(10).join(g)}
  </worldbody>
</mujoco>
"""
(OUT / "scene_datacenter.xml").write_text(scene)

# Go2 with a thermal camera pod on its back (visual only; the base has an explicit inertial)
POD = """      <geom name="thermal_mast" type="cylinder" size="0.012 0.03" pos="0.12 0 0.085" material="black" class="visual"/>
      <geom name="thermal_head" type="box" size="0.035 0.055 0.028" pos="0.13 0 0.14" rgba="0.18 0.19 0.21 1" class="visual"/>
      <geom name="thermal_lens" type="cylinder" size="0.02 0.004" pos="0.167 -0.018 0.14" zaxis="1 0 0" rgba="0.05 0.06 0.1 1" class="visual"/>
      <geom name="thermal_lens_ring" type="cylinder" size="0.024 0.002" pos="0.166 -0.018 0.14" zaxis="1 0 0" rgba="0.9 0.45 0.1 1" class="visual"/>
      <geom name="rgb_lens" type="cylinder" size="0.01 0.004" pos="0.167 0.025 0.14" zaxis="1 0 0" rgba="0.05 0.06 0.1 1" class="visual"/>
      <geom name="status_led" type="sphere" size="0.006" pos="0.13 0.04 0.169" rgba="0.2 1 0.35 1" class="visual"/>
"""
src = (OUT / "go2.xml").read_text()
anchor = '<body name="base" pos="0 0 0.445" childclass="go2">\n'
assert anchor in src
(OUT / "go2_thermal.xml").write_text(src.replace(anchor, anchor + POD).replace('model="go2"', 'model="go2 thermal"'))
print(f"wrote scene_datacenter.xml ({len(g)} geoms, {len(lights)} lights) and go2_thermal.xml")

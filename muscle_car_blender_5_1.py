import math
import traceback

import bmesh
import bpy
from mathutils import Vector


CAR_LENGTH = 4.8
CAR_HALF_WIDTH = 1.0
CAR_HEIGHT = 1.28
FRONT_AXLE_Y = 1.40
REAR_AXLE_Y = -1.40


def smooth_object(obj):
    if obj and obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True


def link_to_collection(obj, collection):
    collection.objects.link(obj)


def assign_material(obj, material):
    if obj.type != "MESH":
        return
    obj.data.materials.clear()
    obj.data.materials.append(material)


def make_mesh_object(name, verts, faces, collection, material=None, smooth=True):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link_to_collection(obj, collection)
    if material:
        assign_material(obj, material)
    if smooth:
        smooth_object(obj)
    return obj


def make_bmesh_object(name, bm, collection, material=None, smooth=True):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link_to_collection(obj, collection)
    if material:
        assign_material(obj, material)
    if smooth:
        smooth_object(obj)
    return obj


def add_box(name, min_corner, max_corner, collection, material=None, smooth=True):
    # Normalize bounds so mirrored-side callers can pass coordinates in either order.
    x0, x1 = sorted((min_corner[0], max_corner[0]))
    y0, y1 = sorted((min_corner[1], max_corner[1]))
    z0, z1 = sorted((min_corner[2], max_corner[2]))
    verts = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=smooth)


def create_cylinder(name, radius, depth, segments, collection, material=None, smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    return make_bmesh_object(name, bm, collection, material=material, smooth=smooth)


def create_torus(name, major_r, minor_r, u_segments, v_segments, collection, material=None, smooth=True):
    verts = []
    faces = []
    for i in range(u_segments):
        u = (i / u_segments) * math.tau
        cu = math.cos(u)
        su = math.sin(u)
        for j in range(v_segments):
            v = (j / v_segments) * math.tau
            cv = math.cos(v)
            sv = math.sin(v)
            x = (major_r + minor_r * cv) * cu
            y = (major_r + minor_r * cv) * su
            z = minor_r * sv
            verts.append((x, y, z))
    for i in range(u_segments):
        i2 = (i + 1) % u_segments
        for j in range(v_segments):
            j2 = (j + 1) % v_segments
            a = i * v_segments + j
            b = i2 * v_segments + j
            c = i2 * v_segments + j2
            d = i * v_segments + j2
            faces.append((a, b, c, d))
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=smooth)


def create_uv_sphere(name, radius, u_segments, v_segments, collection, material=None, smooth=True):
    verts = []
    faces = []
    for v in range(v_segments + 1):
        phi = math.pi * (v / v_segments)
        sp = math.sin(phi)
        cp = math.cos(phi)
        for u in range(u_segments):
            theta = math.tau * (u / u_segments)
            ct = math.cos(theta)
            st = math.sin(theta)
            x = radius * sp * ct
            y = radius * sp * st
            z = radius * cp
            verts.append((x, y, z))
    ring = u_segments
    for v in range(v_segments):
        for u in range(u_segments):
            u2 = (u + 1) % u_segments
            a = v * ring + u
            b = v * ring + u2
            c = (v + 1) * ring + u2
            d = (v + 1) * ring + u
            if v == 0:
                faces.append((a, c, d))
            elif v == v_segments - 1:
                faces.append((a, b, c))
            else:
                faces.append((a, b, c, d))
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=smooth)


def create_disc_lens(name, radius, depth, segments, collection, material=None):
    verts = []
    faces = []
    half_d = depth * 0.5
    verts.append((0.0, half_d, 0.0))
    verts.append((0.0, -half_d, 0.0))
    for i in range(segments):
        a = math.tau * i / segments
        x = radius * math.cos(a)
        z = radius * math.sin(a)
        verts.append((x, half_d, z))
    for i in range(segments):
        a = math.tau * i / segments
        x = radius * math.cos(a)
        z = radius * math.sin(a)
        verts.append((x, -half_d, z))
    front_center = 0
    back_center = 1
    front_start = 2
    back_start = 2 + segments
    for i in range(segments):
        i2 = (i + 1) % segments
        faces.append((front_center, front_start + i, front_start + i2))
        faces.append((back_center, back_start + i2, back_start + i))
        faces.append((front_start + i, back_start + i, back_start + i2, front_start + i2))
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=True)


def create_beam_box(name, p0, p1, width, height, collection, material=None, smooth=True):
    a = Vector(p0)
    b = Vector(p1)
    axis = b - a
    length = axis.length
    if length < 1.0e-6:
        return None

    fwd = axis.normalized()
    ref = Vector((0.0, 0.0, 1.0))
    if abs(fwd.dot(ref)) > 0.95:
        ref = Vector((0.0, 1.0, 0.0))
    right = fwd.cross(ref).normalized()
    up = right.cross(fwd).normalized()
    hw = width * 0.5
    hh = height * 0.5

    c0 = a
    c1 = b
    verts = [
        tuple(c0 + right * hw + up * hh),
        tuple(c0 - right * hw + up * hh),
        tuple(c0 - right * hw - up * hh),
        tuple(c0 + right * hw - up * hh),
        tuple(c1 + right * hw + up * hh),
        tuple(c1 - right * hw + up * hh),
        tuple(c1 - right * hw - up * hh),
        tuple(c1 + right * hw - up * hh),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=smooth)


def create_thick_panel(name, p0, p1, p2, p3, thickness, collection, material=None, smooth=True):
    v0 = Vector(p0)
    v1 = Vector(p1)
    v2 = Vector(p2)
    v3 = Vector(p3)
    normal = (v1 - v0).cross(v3 - v0).normalized()
    offset = normal * (thickness * 0.5)
    front = [v0 + offset, v1 + offset, v2 + offset, v3 + offset]
    back = [v0 - offset, v1 - offset, v2 - offset, v3 - offset]
    verts = [tuple(v) for v in (front + back)]
    faces = [
        (0, 1, 2, 3),
        (7, 6, 5, 4),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=smooth)


def add_mirror_and_subsurf(obj):
    mirror = obj.modifiers.new("Mirror", "MIRROR")
    mirror.use_axis[0] = True
    mirror.use_clip = True
    subsurf = obj.modifiers.new("Subsurf", "SUBSURF")
    subsurf.levels = 2
    subsurf.render_levels = 3


def clear_scene_data():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for curve in list(bpy.data.curves):
        if curve.users == 0:
            bpy.data.curves.remove(curve)
    for cam in list(bpy.data.cameras):
        if cam.users == 0:
            bpy.data.cameras.remove(cam)
    for light in list(bpy.data.lights):
        if light.users == 0:
            bpy.data.lights.remove(light)
    for col in list(bpy.data.collections):
        if col.users == 0:
            bpy.data.collections.remove(col)


def clear_worlds_and_create(scene):
    for world in list(bpy.data.worlds):
        bpy.data.worlds.remove(world, do_unlink=True)
    world = bpy.data.worlds.new("StudioBlackWorld")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    bg = nodes.new("ShaderNodeBackground")
    out = nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value = (0.02, 0.02, 0.025, 1.0)
    bg.inputs["Strength"].default_value = 0.0
    links.new(bg.outputs["Background"], out.inputs["Surface"])


def set_viewport_scene_lighting():
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.use_scene_lights = True
                    space.shading.use_scene_world = True


def set_principled_input(bsdf, keys, value):
    for key in keys:
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = value
            return True
    return False


def make_principled_material(
    name,
    base_color,
    metallic=0.0,
    roughness=0.5,
    transmission=0.0,
    ior=1.45,
    emission_color=None,
    emission_strength=0.0,
    alpha=1.0,
):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (base_color[0], base_color[1], base_color[2], alpha)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    set_principled_input(bsdf, ["Base Color"], base_color)
    set_principled_input(bsdf, ["Metallic"], metallic)
    set_principled_input(bsdf, ["Roughness"], roughness)
    set_principled_input(bsdf, ["Transmission Weight", "Transmission"], transmission)
    set_principled_input(bsdf, ["IOR"], ior)
    set_principled_input(bsdf, ["Alpha"], alpha)
    if emission_color is not None:
        set_principled_input(bsdf, ["Emission Color", "Emission"], emission_color)
        set_principled_input(bsdf, ["Emission Strength"], emission_strength)
        mat.diffuse_color = (
            emission_color[0],
            emission_color[1],
            emission_color[2],
            alpha,
        )
    return mat


def create_material_library():
    print("Creating materials...")
    mats = {}
    mats["body"] = make_principled_material(
        "M_BodyPaint",
        (0.95, 0.72, 0.00, 1.0),
        metallic=0.2,
        roughness=0.03,
    )
    mats["hood"] = make_principled_material(
        "M_HoodMatte",
        (0.03, 0.03, 0.03, 1.0),
        metallic=0.0,
        roughness=0.55,
    )
    mats["chrome"] = make_principled_material(
        "M_Chrome",
        (0.85, 0.85, 0.85, 1.0),
        metallic=1.0,
        roughness=0.12,
    )
    mats["alu"] = make_principled_material(
        "M_BrushedAlu",
        (0.65, 0.65, 0.68, 1.0),
        metallic=1.0,
        roughness=0.22,
    )
    mats["rubber"] = make_principled_material(
        "M_Rubber",
        (0.03, 0.03, 0.03, 1.0),
        metallic=0.0,
        roughness=0.95,
    )
    mats["rim"] = make_principled_material(
        "M_RimsGunmetal",
        (0.08, 0.08, 0.09, 1.0),
        metallic=0.85,
        roughness=0.25,
    )
    mats["caliper"] = make_principled_material(
        "M_CaliperRed",
        (0.80, 0.12, 0.02, 1.0),
        metallic=0.2,
        roughness=0.35,
    )
    mats["carbon"] = make_principled_material(
        "M_Carbon",
        (0.04, 0.04, 0.04, 1.0),
        metallic=0.05,
        roughness=0.30,
    )
    mats["seat"] = make_principled_material(
        "M_SeatLeather",
        (0.10, 0.02, 0.02, 1.0),
        metallic=0.0,
        roughness=0.72,
    )
    mats["alcantara"] = make_principled_material(
        "M_Alcantara",
        (0.08, 0.05, 0.05, 1.0),
        metallic=0.0,
        roughness=0.88,
    )
    mats["dash"] = make_principled_material(
        "M_Dashboard",
        (0.04, 0.04, 0.05, 1.0),
        metallic=0.0,
        roughness=0.65,
    )
    mats["interior"] = make_principled_material(
        "M_InteriorTrim",
        (0.04, 0.04, 0.04, 1.0),
        metallic=0.0,
        roughness=0.80,
    )
    mats["headlight"] = make_principled_material(
        "M_HeadlightEmit",
        (1.0, 0.97, 0.88, 1.0),
        metallic=0.0,
        roughness=0.02,
        emission_color=(1.0, 0.97, 0.88, 1.0),
        emission_strength=8.0,
    )
    mats["taillight"] = make_principled_material(
        "M_TailLightEmit",
        (0.85, 0.0, 0.0, 1.0),
        metallic=0.0,
        roughness=0.04,
        emission_color=(0.85, 0.0, 0.0, 1.0),
        emission_strength=10.0,
    )
    mats["indicator"] = make_principled_material(
        "M_IndicatorEmit",
        (1.0, 0.55, 0.0, 1.0),
        metallic=0.0,
        roughness=0.04,
        emission_color=(1.0, 0.55, 0.0, 1.0),
        emission_strength=6.0,
    )
    mats["gauges"] = make_principled_material(
        "M_GaugesEmit",
        (0.0, 0.80, 0.30, 1.0),
        metallic=0.0,
        roughness=0.5,
        emission_color=(0.0, 0.80, 0.30, 1.0),
        emission_strength=3.0,
    )
    mats["ground"] = make_principled_material(
        "M_GroundAsphalt",
        (0.04, 0.04, 0.04, 1.0),
        metallic=0.0,
        roughness=0.90,
    )
    mats["glass"] = make_principled_material(
        "M_Glass",
        (0.65, 0.82, 0.95, 1.0),
        metallic=0.0,
        roughness=0.02,
        transmission=0.92,
        ior=1.52,
        alpha=0.25,
    )
    mats["glass"].diffuse_color = (0.65, 0.82, 0.95, 0.25)
    mats["glass"].use_backface_culling = False
    try:
        mats["glass"].surface_render_method = "DITHERED"
    except Exception:
        pass
    try:
        mats["glass"].blend_method = "HASHED"
    except Exception:
        pass
    try:
        mats["glass"].shadow_method = "HASHED"
    except Exception:
        pass
    return mats


def body_station_profile(y):
    # Width and vertical profile tuned for modern muscle silhouette.
    width = (
        0.62
        + 0.28 * math.exp(-((y + 1.35) / 0.78) ** 2)
        + 0.10 * math.exp(-((y - 0.10) / 1.1) ** 2)
        - 0.22 * math.exp(-((y - 2.22) / 0.28) ** 2)
        - 0.18 * math.exp(-((y + 2.20) / 0.35) ** 2)
    )
    width = max(0.18, min(CAR_HALF_WIDTH, width))
    belt = (
        0.66
        + 0.08 * math.exp(-((y + 1.25) / 0.9) ** 2)
        + 0.05 * math.exp(-((y - 0.05) / 1.3) ** 2)
        - 0.10 * math.exp(-((y - 2.2) / 0.33) ** 2)
    )
    roof = (
        1.10
        + 0.12 * math.exp(-((y + 0.40) / 0.95) ** 2)
        - 0.20 * math.exp(-((y - 1.00) / 0.50) ** 2)
        - 0.18 * math.exp(-((y + 1.82) / 0.40) ** 2)
    )
    roof = max(0.92, min(1.26, roof))
    return width, belt, roof


def set_edge_creases(mesh, edge_key_set, crease_value=1.0):
    # Blender 4.x/5.x supports edge.crease; keep fallback for compatibility.
    for e in mesh.edges:
        k = tuple(sorted((e.vertices[0], e.vertices[1])))
        if k in edge_key_set:
            try:
                e.crease = crease_value
            except Exception:
                pass
    if "crease_edge" in mesh.attributes:
        crease_attr = mesh.attributes["crease_edge"]
        for i, e in enumerate(mesh.edges):
            k = tuple(sorted((e.vertices[0], e.vertices[1])))
            if k in edge_key_set:
                crease_attr.data[i].value = crease_value


def build_body(ctx):
    print("Building body loft meshes...")
    exterior = ctx["collections"]["Exterior"]
    mats = ctx["materials"]
    station_count = 20
    ys = [CAR_LENGTH * 0.5 - i * (CAR_LENGTH / (station_count - 1)) for i in range(station_count)]
    profiles = [body_station_profile(y) for y in ys]

    # Lower body: 7 points from underfloor to beltline.
    lower_bm = bmesh.new()
    lower_rings = []
    lower_crease_keys = set()

    for i, y in enumerate(ys):
        width, belt, _roof = profiles[i]
        floor_bias = 0.02 * math.exp(-((y + 0.2) / 1.3) ** 2)
        zvals = [
            0.05 + floor_bias,
            0.08 + floor_bias,
            0.13,
            0.25,
            max(0.40, belt - 0.24),
            max(0.54, belt - 0.10),
            belt,
        ]
        xvals = [
            0.00,
            width * 0.19,
            width * 0.42,
            width * 0.66,
            width * 0.82,  # character line
            width * 0.93,
            width * 1.00,  # beltline
        ]
        ring = []
        for x, z in zip(xvals, zvals):
            ring.append(lower_bm.verts.new((x, y, z)))
        lower_rings.append(ring)
    lower_bm.verts.ensure_lookup_table()
    for i in range(station_count - 1):
        r0 = lower_rings[i]
        r1 = lower_rings[i + 1]
        for j in range(6):
            lower_bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
        lower_crease_keys.add(tuple(sorted((r0[4].index, r1[4].index))))
    lower_bm.normal_update()
    lower_obj = make_bmesh_object("CarBody_Lower", lower_bm, exterior, material=mats["body"], smooth=True)

    # Apply character-line crease after bm.to_mesh().
    set_edge_creases(lower_obj.data, lower_crease_keys, crease_value=1.0)
    add_mirror_and_subsurf(lower_obj)

    # Upper shell: separate hood + rear groups, no stitching across greenhouse gap.
    upper_bm = bmesh.new()
    upper_groups = []
    hood_indices = [i for i, y in enumerate(ys) if y > 0.72]
    rear_indices = [i for i, y in enumerate(ys) if y < -0.95]
    upper_groups.append(hood_indices)
    upper_groups.append(rear_indices)

    upper_rings = {}
    for grp in upper_groups:
        for i in grp:
            if i in upper_rings:
                continue
            y = ys[i]
            width, belt, roof = profiles[i]
            shoulder_z = min(CAR_HEIGHT, belt + 0.15)
            roof_edge_z = min(CAR_HEIGHT, roof - 0.03)
            roof_center_z = min(CAR_HEIGHT, roof)
            xvals = [
                width * 0.98,  # beltline base
                width * 0.82,  # upper shoulder
                width * 0.58,  # roof edge
                0.00,          # roof center
            ]
            zvals = [
                belt,
                shoulder_z,
                roof_edge_z,
                roof_center_z,
            ]
            ring = []
            for x, z in zip(xvals, zvals):
                ring.append(upper_bm.verts.new((x, y, z)))
            upper_rings[i] = ring

    upper_bm.verts.ensure_lookup_table()
    for grp in upper_groups:
        for a, b in zip(grp[:-1], grp[1:]):
            r0 = upper_rings[a]
            r1 = upper_rings[b]
            for j in range(3):
                upper_bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
    upper_bm.normal_update()
    upper_obj = make_bmesh_object("CarBody_Upper", upper_bm, exterior, material=mats["body"], smooth=True)
    add_mirror_and_subsurf(upper_obj)

    return {
        "ys": ys,
        "profiles": profiles,
    }


def build_hood(ctx, body_data):
    print("Building hood panels...")
    ext = ctx["collections"]["Exterior"]
    mats = ctx["materials"]

    add_box(
        "Hood_Panel",
        (-0.70, 0.44, 0.81),
        (0.70, 1.98, 0.84),
        ext,
        material=mats["hood"],
        smooth=False,
    )
    add_box(
        "Hood_Spine",
        (-0.06, 0.48, 0.84),
        (0.06, 1.92, 0.875),
        ext,
        material=mats["carbon"],
        smooth=False,
    )
    # Carbon shut line trim around hood opening.
    add_box("Hood_ShutLine_Front", (-0.68, 1.97, 0.835), (0.68, 1.99, 0.845), ext, material=mats["carbon"], smooth=False)
    add_box("Hood_ShutLine_Rear", (-0.68, 0.45, 0.835), (0.68, 0.47, 0.845), ext, material=mats["carbon"], smooth=False)
    add_box("Hood_ShutLine_R", (0.67, 0.47, 0.835), (0.69, 1.97, 0.845), ext, material=mats["carbon"], smooth=False)
    add_box("Hood_ShutLine_L", (-0.69, 0.47, 0.835), (-0.67, 1.97, 0.845), ext, material=mats["carbon"], smooth=False)


def build_greenhouse(ctx, body_data):
    print("Building greenhouse structure (pillars + roof)...")
    ext = ctx["collections"]["Exterior"]
    mats = ctx["materials"]

    # Explicit A/B/C pillars as carbon box beams.
    pillars = [
        ("Pillar_A_R", (0.97, 0.72, 0.74), (0.53, 0.24, 1.08)),
        ("Pillar_B_R", (0.94, -0.04, 0.76), (0.62, -0.44, 1.08)),
        ("Pillar_C_R", (0.90, -0.95, 0.78), (0.50, -1.33, 1.04)),
        ("Pillar_A_L", (-0.97, 0.72, 0.74), (-0.53, 0.24, 1.08)),
        ("Pillar_B_L", (-0.94, -0.04, 0.76), (-0.62, -0.44, 1.08)),
        ("Pillar_C_L", (-0.90, -0.95, 0.78), (-0.50, -1.33, 1.04)),
    ]
    for name, p0, p1 in pillars:
        create_beam_box(name, p0, p1, width=0.05, height=0.07, collection=ext, material=mats["carbon"], smooth=False)

    # Roof panel between A and C pillars.
    create_thick_panel(
        "Roof_Panel",
        (0.53, 0.24, 1.08),
        (-0.53, 0.24, 1.08),
        (-0.50, -1.33, 1.04),
        (0.50, -1.33, 1.04),
        thickness=0.02,
        collection=ext,
        material=mats["carbon"],
        smooth=True,
    )

    # Header and rear roof trims.
    add_box("Header_Bar", (-0.55, 0.22, 1.075), (0.55, 0.25, 1.105), ext, material=mats["carbon"], smooth=False)
    add_box("Rear_Roof_Bar", (-0.52, -1.34, 1.02), (0.52, -1.30, 1.06), ext, material=mats["carbon"], smooth=False)


def build_glass(ctx, body_data):
    print("Building glass panels...")
    glass_col = ctx["collections"]["Glass"]
    mats = ctx["materials"]

    # Windshield: beltline cowl to A-pillar header.
    create_thick_panel(
        "Windshield",
        (0.96, 0.72, 0.74),
        (-0.96, 0.72, 0.74),
        (-0.52, 0.24, 1.08),
        (0.52, 0.24, 1.08),
        thickness=0.012,
        collection=glass_col,
        material=mats["glass"],
        smooth=True,
    )

    # Side windows fill skipped greenhouse zone: beltline bottom to roofline top.
    create_thick_panel(
        "SideGlass_R",
        (0.98, 0.72, 0.74),
        (0.98, -0.95, 0.78),
        (0.50, -1.33, 1.04),
        (0.56, 0.24, 1.08),
        thickness=0.01,
        collection=glass_col,
        material=mats["glass"],
        smooth=True,
    )
    create_thick_panel(
        "SideGlass_L",
        (-0.98, 0.72, 0.74),
        (-0.98, -0.95, 0.78),
        (-0.50, -1.33, 1.04),
        (-0.56, 0.24, 1.08),
        thickness=0.01,
        collection=glass_col,
        material=mats["glass"],
        smooth=True,
    )

    # Rear glass between C-pillars.
    create_thick_panel(
        "RearGlass",
        (0.50, -1.33, 1.04),
        (-0.50, -1.33, 1.04),
        (-0.86, -1.67, 0.78),
        (0.86, -1.67, 0.78),
        thickness=0.012,
        collection=glass_col,
        material=mats["glass"],
        smooth=True,
    )


def build_supercharger(ctx):
    print("Building supercharger + velocity stacks...")
    ext = ctx["collections"]["Exterior"]
    mats = ctx["materials"]

    add_box("Blower_Box", (-0.22, 0.54, 0.84), (0.22, 0.92, 1.02), ext, material=mats["chrome"], smooth=True)
    add_box("Blower_Base", (-0.26, 0.50, 0.82), (0.26, 0.96, 0.86), ext, material=mats["alu"], smooth=True)

    xs = (-0.10, 0.10)
    ys = (0.60, 0.73, 0.86)
    idx = 0
    for sx in xs:
        for sy in ys:
            stack = create_cylinder(f"VelocityStack_{idx}", radius=0.035, depth=0.24, segments=24, collection=ext, material=mats["chrome"], smooth=True)
            stack.location = (sx, sy, 1.08)
            idx += 1


def build_front(ctx):
    print("Building front fascia...")
    ext = ctx["collections"]["Exterior"]
    mats = ctx["materials"]

    # Front fascia is explicitly biased toward +Y so it reads as nose-forward in bird's-eye view.
    add_box("Front_Bumper", (-0.94, 2.10, 0.12), (0.94, 2.34, 0.58), ext, material=mats["body"], smooth=True)
    add_box("Front_Grille_Frame", (-0.56, 2.26, 0.30), (0.56, 2.39, 0.56), ext, material=mats["carbon"], smooth=False)
    for i, z in enumerate((0.34, 0.40, 0.46, 0.52)):
        add_box(f"Grille_Bar_{i}", (-0.53, 2.355, z), (0.53, 2.375, z + 0.012), ext, material=mats["chrome"], smooth=False)

    # Recessed projector headlights and DRL strips.
    for side in (-1.0, 1.0):
        lens = create_disc_lens(
            f"HeadProjector_{'L' if side < 0 else 'R'}",
            radius=0.08,
            depth=0.05,
            segments=28,
            collection=ext,
            material=mats["headlight"],
        )
        lens.location = (0.78 * side, 2.34, 0.58)
        lens.rotation_euler = (math.pi * 0.5, 0.0, 0.0)

        ring = create_cylinder(
            f"HeadReflectorRing_{'L' if side < 0 else 'R'}",
            radius=0.095,
            depth=0.018,
            segments=32,
            collection=ext,
            material=mats["chrome"],
            smooth=True,
        )
        ring.location = (0.78 * side, 2.31, 0.58)
        ring.rotation_euler = (math.pi * 0.5, 0.0, 0.0)

        add_box(
            f"DRL_{'L' if side < 0 else 'R'}",
            (0.66 * side - 0.13 * side, 2.30, 0.47),
            (0.66 * side + 0.13 * side, 2.32, 0.50),
            ext,
            material=mats["headlight"],
            smooth=False,
        )

    # Front splitter with fins.
    add_box("FrontSplitter_Main", (-0.90, 2.34, 0.05), (0.90, 2.50, 0.10), ext, material=mats["carbon"], smooth=False)
    add_box("Splitter_Fin_R1", (0.38, 2.35, 0.05), (0.42, 2.49, 0.14), ext, material=mats["carbon"], smooth=False)
    add_box("Splitter_Fin_L1", (-0.42, 2.35, 0.05), (-0.38, 2.49, 0.14), ext, material=mats["carbon"], smooth=False)
    add_box("Splitter_Fin_R2", (0.68, 2.35, 0.05), (0.72, 2.49, 0.14), ext, material=mats["carbon"], smooth=False)
    add_box("Splitter_Fin_L2", (-0.72, 2.35, 0.05), (-0.68, 2.49, 0.14), ext, material=mats["carbon"], smooth=False)


def create_rear_corner_wrap(name, side, collection, material):
    s = side
    # Faceted quarter-wrap that tapers toward the wheel opening.
    verts = [
        (s * 0.72, -2.54, 0.12),  # inner rear lower
        (s * 0.94, -2.62, 0.12),  # outer rear lower
        (s * 0.94, -2.62, 0.46),  # outer rear upper
        (s * 0.78, -2.54, 0.52),  # inner rear upper
        (s * 0.84, -2.40, 0.18),  # inner front lower (toward wheel cutout)
        (s * 0.98, -2.48, 0.20),  # outer front lower
        (s * 0.98, -2.48, 0.50),  # outer front upper
        (s * 0.82, -2.40, 0.56),  # inner front upper
    ]
    faces = [
        (0, 1, 2, 3),  # rear face
        (4, 7, 6, 5),  # front taper face
        (0, 4, 5, 1),  # lower face
        (3, 2, 6, 7),  # upper face
        (0, 3, 7, 4),  # inner face
        (1, 5, 6, 2),  # outer face
    ]
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=True)


def build_rear(ctx):
    print("Building rear fascia + taillights + diffuser...")
    ext = ctx["collections"]["Exterior"]
    mats = ctx["materials"]

    # Rear bumper shell: lower mass + upper cap to avoid "inside body" appearance.
    add_box("Rear_Bumper", (-0.72, -2.62, 0.10), (0.72, -2.50, 0.46), ext, material=mats["body"], smooth=True)
    add_box("Rear_Bumper_Upper", (-0.68, -2.54, 0.40), (0.68, -2.44, 0.60), ext, material=mats["body"], smooth=True)
    create_rear_corner_wrap("RearCornerWrap_R", 1.0, ext, mats["body"])
    create_rear_corner_wrap("RearCornerWrap_L", -1.0, ext, mats["body"])

    # Integrated ducktail at the true trailing edge.
    add_box("Ducktail_Spoiler", (-0.84, -2.46, 0.84), (0.84, -2.36, 0.90), ext, material=mats["body"], smooth=True)
    add_box("Ducktail_Lip", (-0.84, -2.54, 0.89), (0.84, -2.46, 0.95), ext, material=mats["body"], smooth=True)
    add_box("Trunk_ShutLine", (-0.86, -2.35, 0.83), (0.86, -2.33, 0.85), ext, material=mats["carbon"], smooth=False)

    add_box("TailLight_Bar", (-0.82, -2.58, 0.50), (0.82, -2.54, 0.59), ext, material=mats["taillight"], smooth=False)
    add_box("TailCluster_R", (0.68, -2.59, 0.46), (0.88, -2.53, 0.61), ext, material=mats["taillight"], smooth=False)
    add_box("TailCluster_L", (-0.88, -2.59, 0.46), (-0.68, -2.53, 0.61), ext, material=mats["taillight"], smooth=False)
    add_box("Rear_Indicator_R", (0.54, -2.58, 0.47), (0.64, -2.54, 0.53), ext, material=mats["indicator"], smooth=False)
    add_box("Rear_Indicator_L", (-0.64, -2.58, 0.47), (-0.54, -2.54, 0.53), ext, material=mats["indicator"], smooth=False)

    # Closeout panels to seal the rear opening and form a proper rear deck wall.
    create_thick_panel(
        "Rear_Closure_Upper",
        (0.80, -2.36, 0.62),
        (-0.80, -2.36, 0.62),
        (-0.68, -2.20, 0.86),
        (0.68, -2.20, 0.86),
        thickness=0.03,
        collection=ext,
        material=mats["body"],
        smooth=True,
    )
    add_box("Rear_Closure_Lower", (-0.80, -2.48, 0.44), (0.80, -2.36, 0.62), ext, material=mats["body"], smooth=True)
    add_box("Rear_Closure_Side_R", (0.80, -2.40, 0.52), (0.92, -2.22, 0.78), ext, material=mats["body"], smooth=True)
    add_box("Rear_Closure_Side_L", (-0.92, -2.40, 0.52), (-0.80, -2.22, 0.78), ext, material=mats["body"], smooth=True)

    # Rear diffuser with tunnel channels.
    add_box("RearDiffuser_Main", (-0.76, -2.63, 0.04), (0.76, -2.52, 0.18), ext, material=mats["carbon"], smooth=False)
    add_box("Diffuser_TunnelWall_R", (0.18, -2.62, 0.04), (0.22, -2.52, 0.18), ext, material=mats["carbon"], smooth=False)
    add_box("Diffuser_TunnelWall_C", (-0.02, -2.62, 0.04), (0.02, -2.52, 0.18), ext, material=mats["carbon"], smooth=False)
    add_box("Diffuser_TunnelWall_L", (-0.22, -2.62, 0.04), (-0.18, -2.52, 0.18), ext, material=mats["carbon"], smooth=False)


def create_fender_flare(name, side, cy, cz, collection, material):
    segs = 18
    start_a = math.radians(210.0)
    end_a = math.radians(340.0)
    x_inner = side * 0.90
    x_outer = side * 0.985
    r_inner = 0.39
    r_outer = 0.46
    verts = []
    faces = []

    def arc_point(xv, r, a):
        return (xv, cy + r * math.cos(a), cz + r * math.sin(a))

    for row in range(4):
        for i in range(segs + 1):
            t = i / segs
            a = start_a + t * (end_a - start_a)
            if row == 0:
                verts.append(arc_point(x_inner, r_inner, a))
            elif row == 1:
                verts.append(arc_point(x_inner, r_outer, a))
            elif row == 2:
                verts.append(arc_point(x_outer, r_outer, a))
            else:
                verts.append(arc_point(x_outer, r_inner, a))

    row_len = segs + 1
    for r in range(3):
        for i in range(segs):
            a = r * row_len + i
            b = a + 1
            c = (r + 1) * row_len + i + 1
            d = (r + 1) * row_len + i
            faces.append((a, b, c, d))

    return make_mesh_object(name, verts, faces, collection, material=material, smooth=True)


def build_sides(ctx):
    print("Building side aero and detailing...")
    ext = ctx["collections"]["Exterior"]
    mats = ctx["materials"]

    add_box("Rocker_R", (0.90, -1.78, 0.10), (0.98, 1.76, 0.24), ext, material=mats["body"], smooth=True)
    add_box("Rocker_L", (-0.98, -1.78, 0.10), (-0.90, 1.76, 0.24), ext, material=mats["body"], smooth=True)

    create_fender_flare("RearFlare_R", 1.0, REAR_AXLE_Y, 0.40, ext, mats["body"])
    create_fender_flare("RearFlare_L", -1.0, REAR_AXLE_Y, 0.40, ext, mats["body"])

    # Quarter vents with louvres.
    add_box("QuarterVent_R_Frame", (0.905, -1.16, 0.45), (0.985, -0.90, 0.67), ext, material=mats["carbon"], smooth=False)
    add_box("QuarterVent_L_Frame", (-0.985, -1.16, 0.45), (-0.905, -0.90, 0.67), ext, material=mats["carbon"], smooth=False)
    for i in range(4):
        z0 = 0.48 + i * 0.045
        add_box(f"QuarterLouvre_R_{i}", (0.915, -1.14, z0), (0.975, -0.93, z0 + 0.012), ext, material=mats["alu"], smooth=False)
        add_box(f"QuarterLouvre_L_{i}", (-0.975, -1.14, z0), (-0.915, -0.93, z0 + 0.012), ext, material=mats["alu"], smooth=False)

    # Door mirrors + mirror glass.
    add_box("MirrorHousing_R", (0.98, 0.48, 0.84), (1.12, 0.64, 0.94), ext, material=mats["body"], smooth=True)
    add_box("MirrorHousing_L", (-1.12, 0.48, 0.84), (-0.98, 0.64, 0.94), ext, material=mats["body"], smooth=True)
    create_thick_panel(
        "MirrorGlass_R",
        (1.115, 0.50, 0.85),
        (1.115, 0.62, 0.85),
        (1.115, 0.62, 0.92),
        (1.115, 0.50, 0.92),
        thickness=0.005,
        collection=ext,
        material=mats["glass"],
        smooth=True,
    )
    create_thick_panel(
        "MirrorGlass_L",
        (-1.115, 0.50, 0.85),
        (-1.115, 0.62, 0.85),
        (-1.115, 0.62, 0.92),
        (-1.115, 0.50, 0.92),
        thickness=0.005,
        collection=ext,
        material=mats["glass"],
        smooth=True,
    )


def build_exhausts(ctx):
    print("Building side-exit exhausts...")
    ext = ctx["collections"]["Exterior"]
    mats = ctx["materials"]

    pipe_idx = 0
    for side in (-1.0, 1.0):
        for y in (-0.78, -0.60):
            pipe = create_cylinder(
                f"SideExhaust_{pipe_idx}",
                radius=0.036,
                depth=0.30,
                segments=20,
                collection=ext,
                material=mats["chrome"],
                smooth=True,
            )
            pipe.location = (side * 1.02, y, 0.26)
            pipe.rotation_euler = (0.0, math.pi * 0.5, 0.0)
            shield = add_box(
                f"HeatShield_{pipe_idx}",
                (side * 0.96 - 0.06 * side, y - 0.10, 0.22),
                (side * 0.96 + 0.06 * side, y + 0.10, 0.30),
                ext,
                material=mats["alu"],
                smooth=False,
            )
            smooth_object(shield)
            pipe_idx += 1


def create_tapered_spoke(name, inner_r, outer_r, width_inner, width_outer, thickness, collection, material):
    xi = thickness * 0.5
    xo = -thickness * 0.5
    verts = [
        (xi, inner_r, -width_inner * 0.5),
        (xi, inner_r, width_inner * 0.5),
        (xi, outer_r, width_outer * 0.5),
        (xi, outer_r, -width_outer * 0.5),
        (xo, inner_r, -width_inner * 0.5),
        (xo, inner_r, width_inner * 0.5),
        (xo, outer_r, width_outer * 0.5),
        (xo, outer_r, -width_outer * 0.5),
    ]
    faces = [
        (0, 1, 2, 3),
        (7, 6, 5, 4),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=True)


def build_wheel_assembly(ctx, label, cx, cy, cz, tyre_r, tyre_w, rim_r):
    wheels = ctx["collections"]["Wheels"]
    mats = ctx["materials"]
    side = 1.0 if cx > 0 else -1.0

    tyre = create_torus(f"Tyre_{label}", tyre_r, tyre_w * 0.5, 56, 18, wheels, material=mats["rubber"], smooth=True)
    tyre.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    tyre.location = (cx, cy, cz)

    sidewall_ring = create_torus(
        f"TyreSidewall_{label}",
        tyre_r * 0.985,
        tyre_w * 0.08,
        48,
        12,
        wheels,
        material=mats["rubber"],
        smooth=True,
    )
    sidewall_ring.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    sidewall_ring.location = (cx, cy, cz)

    rim = create_cylinder(f"Rim_{label}", rim_r, tyre_w * 0.70, 40, wheels, material=mats["rim"], smooth=True)
    rim.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    rim.location = (cx, cy, cz)

    lip_outer = create_cylinder(f"RimLipOuter_{label}", rim_r * 1.02, 0.012, 40, wheels, material=mats["chrome"], smooth=True)
    lip_outer.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    lip_outer.location = (cx + side * (tyre_w * 0.23), cy, cz)

    lip_inner = create_cylinder(f"RimLipInner_{label}", rim_r * 1.02, 0.012, 40, wheels, material=mats["chrome"], smooth=True)
    lip_inner.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    lip_inner.location = (cx - side * (tyre_w * 0.23), cy, cz)

    for i in range(5):
        spoke = create_tapered_spoke(
            f"Spoke_{label}_{i}",
            inner_r=rim_r * 0.18,
            outer_r=rim_r * 0.90,
            width_inner=rim_r * 0.10,
            width_outer=rim_r * 0.17,
            thickness=0.05,
            collection=wheels,
            material=mats["alu"],
        )
        spoke.location = (cx, cy, cz)
        spoke.rotation_euler = (math.tau * i / 5.0, 0.0, 0.0)

    disc = create_cylinder(f"Disc_{label}", rim_r * 0.62, 0.028, 32, wheels, material=mats["alu"], smooth=True)
    disc.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    disc.location = (cx - side * (tyre_w * 0.12), cy, cz)

    # Ventilation holes represented by through cylinders (dark void look).
    for i in range(8):
        a = math.tau * i / 8.0
        hy = cy + math.cos(a) * rim_r * 0.42
        hz = cz + math.sin(a) * rim_r * 0.42
        hole = create_cylinder(f"DiscVent_{label}_{i}", rim_r * 0.07, 0.032, 18, wheels, material=mats["interior"], smooth=True)
        hole.rotation_euler = (0.0, math.pi * 0.5, 0.0)
        hole.location = (cx - side * (tyre_w * 0.12), hy, hz)

    cal = add_box(
        f"Cal_{label}",
        (cx + side * (tyre_w * 0.10), cy + rim_r * 0.20, cz + rim_r * 0.20),
        (cx + side * (tyre_w * 0.22), cy + rim_r * 0.42, cz + rim_r * 0.48),
        wheels,
        material=mats["caliper"],
        smooth=True,
    )
    smooth_object(cal)

    bolt_a = create_cylinder(f"CalBolt_{label}_A", 0.01, 0.02, 12, wheels, material=mats["chrome"], smooth=True)
    bolt_a.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    bolt_a.location = (cx + side * (tyre_w * 0.23), cy + rim_r * 0.30, cz + rim_r * 0.38)
    bolt_b = create_cylinder(f"CalBolt_{label}_B", 0.01, 0.02, 12, wheels, material=mats["chrome"], smooth=True)
    bolt_b.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    bolt_b.location = (cx + side * (tyre_w * 0.23), cy + rim_r * 0.26, cz + rim_r * 0.28)

    hub = create_cylinder(f"Hub_{label}", rim_r * 0.18, 0.09, 28, wheels, material=mats["chrome"], smooth=True)
    hub.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    hub.location = (cx, cy, cz)
    cap = create_cylinder(f"HubCap_{label}", rim_r * 0.12, 0.04, 28, wheels, material=mats["rim"], smooth=True)
    cap.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    cap.location = (cx + side * 0.03, cy, cz)


def build_wheels(ctx):
    print("Building all wheel assemblies...")
    build_wheel_assembly(ctx, "FR", 1.00, FRONT_AXLE_Y, 0.38, 0.36, 0.225, 0.275)
    build_wheel_assembly(ctx, "FL", -1.00, FRONT_AXLE_Y, 0.38, 0.36, 0.225, 0.275)
    build_wheel_assembly(ctx, "RR", 1.06, REAR_AXLE_Y, 0.40, 0.385, 0.310, 0.295)
    build_wheel_assembly(ctx, "RL", -1.06, REAR_AXLE_Y, 0.40, 0.385, 0.310, 0.295)


def create_gauge_disc(name, radius, collection, material):
    verts = [(0.0, 0.0, 0.0)]
    faces = []
    segs = 24
    for i in range(segs):
        a = math.tau * i / segs
        verts.append((radius * math.cos(a), 0.0, radius * math.sin(a)))
    for i in range(segs):
        i2 = (i + 1) % segs
        faces.append((0, 1 + i, 1 + i2))
    return make_mesh_object(name, verts, faces, collection, material=material, smooth=False)


def build_bucket_seat(name, x, y, z, collection, mats):
    seat_objs = []
    seat_objs.append(add_box(f"{name}_Base", (x - 0.20, y - 0.18, z), (x + 0.20, y + 0.18, z + 0.14), collection, material=mats["seat"], smooth=True))
    # Backrest is on the rear side (-Y), so occupants face toward the nose (+Y).
    seat_objs.append(add_box(f"{name}_Back", (x - 0.19, y - 0.22, z + 0.12), (x + 0.19, y - 0.04, z + 0.66), collection, material=mats["seat"], smooth=True))
    seat_objs.append(add_box(f"{name}_Bolster_R", (x + 0.18, y - 0.16, z + 0.03), (x + 0.24, y + 0.18, z + 0.33), collection, material=mats["seat"], smooth=True))
    seat_objs.append(add_box(f"{name}_Bolster_L", (x - 0.24, y - 0.16, z + 0.03), (x - 0.18, y + 0.18, z + 0.33), collection, material=mats["seat"], smooth=True))
    seat_objs.append(add_box(f"{name}_Headrest", (x - 0.12, y - 0.22, z + 0.62), (x + 0.12, y - 0.14, z + 0.82), collection, material=mats["seat"], smooth=True))
    seat_objs.append(add_box(f"{name}_HarnessSlot", (x - 0.05, y - 0.21, z + 0.56), (x + 0.05, y - 0.18, z + 0.68), collection, material=mats["interior"], smooth=False))
    for o in seat_objs:
        smooth_object(o)


def create_roll_cage_tube(name, p0, p1, radius, collection, material):
    tube = create_cylinder(name, radius=radius, depth=(Vector(p1) - Vector(p0)).length, segments=18, collection=collection, material=material, smooth=True)
    mid = (Vector(p0) + Vector(p1)) * 0.5
    direction = Vector(p1) - Vector(p0)
    tube.location = tuple(mid)
    tube.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return tube


def build_interior(ctx):
    print("Building interior...")
    interior = ctx["collections"]["Interior"]
    mats = ctx["materials"]

    # Floor pan and transmission tunnel.
    add_box("Floor_Pan", (-0.72, -0.95, 0.08), (0.72, 0.70, 0.16), interior, material=mats["interior"], smooth=False)
    add_box("Transmission_Tunnel", (-0.16, -0.70, 0.16), (0.16, 0.52, 0.32), interior, material=mats["interior"], smooth=True)

    # Dashboard main and angled face panel.
    add_box("Dash_Main", (-0.66, 0.42, 0.56), (0.66, 0.70, 0.75), interior, material=mats["dash"], smooth=True)
    face = create_thick_panel(
        "Dash_Face",
        (0.48, 0.44, 0.72),
        (-0.48, 0.44, 0.72),
        (-0.50, 0.58, 0.60),
        (0.50, 0.58, 0.60),
        thickness=0.01,
        collection=interior,
        material=mats["dash"],
        smooth=False,
    )
    smooth_object(face)

    # Gauges (emissive green).
    gx = (-0.18, 0.0, 0.18)
    for i, x in enumerate(gx):
        dial = create_gauge_disc(f"Gauge_{i}", radius=0.055, collection=interior, material=mats["gauges"])
        dial.location = (x, 0.50, 0.66)
        dial.rotation_euler = (math.pi * 0.5, 0.0, 0.0)

    # Seats at requested side positions.
    build_bucket_seat("Seat_Driver", 0.36, -0.22, 0.17, interior, mats)
    build_bucket_seat("Seat_Passenger", -0.36, -0.22, 0.17, interior, mats)

    # Steering wheel: torus rim, spokes, and dash-mounted tilted column.
    wheel = create_torus("SteerWheel", major_r=0.17, minor_r=0.019, u_segments=40, v_segments=14, collection=interior, material=mats["alcantara"], smooth=True)
    wheel.location = (0.36, 0.46, 0.69)
    wheel.rotation_euler = (math.radians(20.0), 0.0, math.pi * 0.5)
    hub = create_cylinder("SteerHub", 0.038, 0.06, 18, interior, material=mats["alu"], smooth=True)
    hub.location = (0.36, 0.46, 0.69)
    hub.rotation_euler = (math.radians(20.0), 0.0, math.pi * 0.5)
    for i in range(3):
        spoke = create_tapered_spoke(
            f"SteerSpoke_{i}",
            inner_r=0.02,
            outer_r=0.14,
            width_inner=0.03,
            width_outer=0.03,
            thickness=0.012,
            collection=interior,
            material=mats["alu"],
        )
        spoke.location = (0.36, 0.46, 0.69)
        spoke.rotation_euler = (math.tau * i / 3.0 + math.radians(20.0), 0.0, 0.0)

    # Explicit dash anchor prevents floor-mounted appearance.
    add_box("SteerColumn_Shroud", (0.27, 0.61, 0.54), (0.39, 0.70, 0.63), interior, material=mats["dash"], smooth=True)
    create_roll_cage_tube(
        "SteerColumn",
        p0=(0.33, 0.64, 0.58),   # dash/firewall side
        p1=(0.35, 0.49, 0.67),   # wheel hub side
        radius=0.024,
        collection=interior,
        material=mats["interior"],
    )

    # Console and shifter.
    add_box("Center_Console", (-0.16, -0.34, 0.26), (0.16, 0.42, 0.46), interior, material=mats["interior"], smooth=True)
    add_box("Console_Lid", (-0.14, -0.26, 0.45), (0.14, 0.00, 0.49), interior, material=mats["dash"], smooth=True)
    add_box("Shifter_Boot", (0.02, 0.08, 0.45), (0.10, 0.16, 0.54), interior, material=mats["alcantara"], smooth=True)
    shifter = create_cylinder("Gear_Shifter", radius=0.009, depth=0.17, segments=12, collection=interior, material=mats["chrome"], smooth=True)
    shifter.location = (0.06, 0.12, 0.58)
    shifter.rotation_euler = (math.radians(25.0), 0.0, 0.0)
    knob = create_uv_sphere("Shifter_Knob", radius=0.028, u_segments=24, v_segments=16, collection=interior, material=mats["chrome"], smooth=True)
    knob.location = (0.06, 0.16, 0.66)

    # Rear-view mirror.
    add_box("RearView_Mirror", (-0.12, 0.24, 1.00), (0.12, 0.28, 1.08), interior, material=mats["interior"], smooth=True)

    # Door cards + armrest + handle.
    for side in (-1.0, 1.0):
        # Push side panels outward so they sit near the inner door skin.
        x_outer = side * 0.90
        x_inner = side * 0.82
        add_box(f"DoorCard_{'R' if side > 0 else 'L'}", (x_inner, -0.72, 0.30), (x_outer, 0.54, 0.68), interior, material=mats["interior"], smooth=True)
        add_box(f"DoorArmrest_{'R' if side > 0 else 'L'}", (side * 0.82, -0.24, 0.46), (side * 0.90, 0.16, 0.54), interior, material=mats["dash"], smooth=True)
        add_box(f"DoorHandle_{'R' if side > 0 else 'L'}", (side * 0.84, 0.22, 0.50), (side * 0.88, 0.30, 0.53), interior, material=mats["chrome"], smooth=True)

    # Roll cage with 9 tube segments.
    cage_segments = [
        ("Cage_MainHoop_R", (0.50, -0.52, 0.22), (0.50, -0.52, 1.00)),
        ("Cage_MainHoop_Top", (0.50, -0.52, 1.00), (-0.50, -0.52, 1.00)),
        ("Cage_MainHoop_L", (-0.50, -0.52, 1.00), (-0.50, -0.52, 0.22)),
        ("Cage_FrontBar_R", (0.50, -0.50, 1.00), (0.47, 0.22, 1.02)),
        ("Cage_FrontBar_L", (-0.50, -0.50, 1.00), (-0.47, 0.22, 1.02)),
        ("Cage_Header", (0.47, 0.22, 1.02), (-0.47, 0.22, 1.02)),
        ("Cage_Diag_1", (0.50, -0.52, 0.95), (-0.50, -0.52, 0.35)),
        ("Cage_Diag_2", (-0.50, -0.52, 0.95), (0.50, -0.52, 0.35)),
        ("Cage_RearBrace", (0.0, -0.52, 1.00), (0.0, -0.92, 0.50)),
    ]
    for name, p0, p1 in cage_segments:
        create_roll_cage_tube(name, p0, p1, radius=0.018, collection=interior, material=mats["carbon"])


def orient_vehicle(ctx):
    # User-facing orientation fix: rotate the whole car 180 deg in top view.
    scene = ctx["scene"]
    root_col = ctx["collections"]["Root"]
    anchor = bpy.data.objects.new("MuscleCar_Root", None)
    scene.collection.objects.link(anchor)
    for obj in root_col.all_objects:
        obj.parent = anchor
    anchor.location = (0.0, 0.0, 0.0)
    anchor.rotation_euler = (0.0, 0.0, math.pi)


def setup_scene():
    print("Setting up scene...")
    scene = bpy.context.scene
    clear_scene_data()
    clear_worlds_and_create(scene)

    # Render configuration.
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 256
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080

    # Collections.
    root = bpy.data.collections.new("MuscleCar_v4")
    scene.collection.children.link(root)
    ext = bpy.data.collections.new("Exterior")
    gla = bpy.data.collections.new("Glass")
    whe = bpy.data.collections.new("Wheels")
    itn = bpy.data.collections.new("Interior")
    root.children.link(ext)
    root.children.link(gla)
    root.children.link(whe)
    root.children.link(itn)

    mats = create_material_library()

    # Camera.
    cam_data = bpy.data.cameras.new("Camera_MuscleCar")
    cam = bpy.data.objects.new("Camera_MuscleCar", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (5.6, 5.0, 2.4)
    target = Vector((0.0, -0.3, 0.58))
    direction = target - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = 50.0
    scene.camera = cam

    # Area lights.
    lights = [
        ("Key_Area", (6.0, 5.0, 8.0), 3000.0, 4.0),
        ("Fill_Area", (-7.0, -1.0, 4.0), 700.0, 6.0),
        ("Rim_Area", (0.0, -8.0, 5.0), 1500.0, 3.0),
        ("Overhead_Area", (0.0, 0.0, 10.0), 800.0, 8.0),
    ]
    for name, loc, energy, size in lights:
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo)
        lo.location = loc
        dir_to_car = Vector((0.0, -0.3, 0.55)) - lo.location
        lo.rotation_euler = dir_to_car.to_track_quat("-Z", "Y").to_euler()

    # Ground plane (from_pydata).
    ground_verts = [(-12.0, -12.0, 0.0), (12.0, -12.0, 0.0), (12.0, 12.0, 0.0), (-12.0, 12.0, 0.0)]
    ground_faces = [(0, 1, 2, 3)]
    ground = make_mesh_object("Ground_Asphalt", ground_verts, ground_faces, scene.collection, material=mats["ground"], smooth=False)
    smooth_object(ground)

    set_viewport_scene_lighting()
    return {
        "scene": scene,
        "materials": mats,
        "collections": {
            "Root": root,
            "Exterior": ext,
            "Glass": gla,
            "Wheels": whe,
            "Interior": itn,
        },
    }


def main():
    try:
        print("=== Procedural Futuristic Muscle Car Build Started ===")
        print("Target: Blender 5.1, Scripting workspace, bpy/bmesh data API only")
        ctx = setup_scene()
        body_data = build_body(ctx)
        build_hood(ctx, body_data)
        build_greenhouse(ctx, body_data)
        build_glass(ctx, body_data)
        build_front(ctx)
        build_rear(ctx)
        build_sides(ctx)
        build_supercharger(ctx)
        build_exhausts(ctx)
        build_wheels(ctx)
        build_interior(ctx)
        orient_vehicle(ctx)
        print("=== Build complete: MuscleCar_v4 generated successfully ===")
    except Exception:
        print("ERROR during build:")
        traceback.print_exc()


if __name__ == "__main__":
    main()

import bpy
import bmesh
import os


def export_meshes(context, directory):
    meshes_dir = os.path.join(directory, "meshes")
    os.makedirs(meshes_dir, exist_ok=True)

    depsgraph = context.evaluated_depsgraph_get()
    mesh_data = []
    for obj in context.scene.objects:
        if obj.type != "MESH":
            continue

        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        mesh.transform(obj.matrix_world)

        materials = mesh.materials

        if not materials:
            obj_name, filepath, material = export_submesh(mesh, obj.name, directory)
            mesh_data.append((obj_name, filepath, material))
        else:
            for i, mat in enumerate(materials):
                obj_name, filepath, material = export_material_submesh(
                    mesh, obj.name, mat, i, directory
                )
                mesh_data.append((obj_name, filepath, material))

        eval_obj.to_mesh_clear()
        print(mesh_data)

    return mesh_data


def export_material_submesh(mesh, obj_name, material, mat_index, directory):
    """Export only the faces with the given material index, preserving UVs."""
    bm = bmesh.new()
    bm.from_mesh(mesh)

    # Get all faces with this material
    faces = [f for f in bm.faces if f.material_index == mat_index]
    if not faces:
        bm.free()
        return

    # Create a new bmesh for the submesh
    sub_bm = bmesh.new()

    # Create a mapping from old verts to new verts
    vert_map = {}
    for face in faces:
        for v in face.verts:
            if v not in vert_map:
                vert_map[v] = sub_bm.verts.new(v.co)

    # Copy UV layer if exists
    uv_layer = bm.loops.layers.uv.active
    if uv_layer:
        sub_uv_layer = sub_bm.loops.layers.uv.new(uv_layer.name)
    else:
        sub_uv_layer = None

    # Create faces and copy UVs
    for face in faces:
        new_verts = [vert_map[v] for v in face.verts]
        new_face = sub_bm.faces.new(new_verts)

        if sub_uv_layer:
            for loop_old, loop_new in zip(face.loops, new_face.loops):
                loop_new[sub_uv_layer].uv = loop_old[uv_layer].uv

    # Update mesh and export
    sub_bm.verts.index_update()
    sub_bm.faces.index_update()
    sub_bm.normal_update()

    sub_mesh = bpy.data.meshes.new(f"{obj_name}_{material.name}_mesh")
    sub_bm.to_mesh(sub_mesh)
    sub_bm.free()

    # Temporary object for export
    temp_obj = bpy.data.objects.new(f"{obj_name}_{material.name}", sub_mesh)
    bpy.context.collection.objects.link(temp_obj)

    filepath = os.path.join(directory, f"meshes/{obj_name}_{material.name}.obj")
    bpy.ops.object.select_all(action="DESELECT")
    temp_obj.select_set(True)

    bpy.ops.wm.obj_export(
        filepath=filepath,
        export_selected_objects=True,
        export_materials=False,
        export_uv=True,
        forward_axis="Y",
        up_axis="Z",
    )

    # Cleanup
    bpy.data.objects.remove(temp_obj, do_unlink=True)
    bpy.data.meshes.remove(sub_mesh, do_unlink=True)
    bm.free()

    return (
        f"{obj_name}_{material.name}",
        f"{obj_name}_{material.name}.obj",
        material.name,
    )


def export_submesh(mesh, obj_name, directory):
    """Export mesh without material"""
    mesh_copy = mesh.copy()
    temp_obj = bpy.data.objects.new(obj_name, mesh_copy)
    bpy.context.collection.objects.link(temp_obj)

    filepath = os.path.join(directory, f"meshes/{obj_name}.obj")
    bpy.ops.wm.obj_export(
        filepath=filepath,
        export_selected_objects=True,
        export_materials=True,
        export_uv=True,
    )

    bpy.data.objects.remove(temp_obj, do_unlink=True)
    bpy.data.meshes.remove(mesh_copy, do_unlink=True)

    return obj_name, f"{obj_name}.obj", None

bl_info = {
    "name": "Bento (Blender to Nori Exporter)",
    "author": "TheCodec",
    "version": (1, 0),
    "blender": (4, 5, 0),
    "location": "File > Export > Export to Nori (.xml)",
    "description": "Exports each object and its material submeshes as separate OBJ files without modifying the scene.",
    "category": "Import-Export",
}

import bpy
import os
from bpy_extras.io_utils import ExportHelper
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

from Bento.export_materials import load_config, export_materials, convert_values
from Bento.export_meshes import export_meshes


def update_sample_count(self, context):
    if self.use_scene_samples:
        scene = context.scene
        renderer = scene.render.engine
        if renderer == "CYCLES":
            self.sample_count = scene.cycles.samples
        elif renderer == "BLENDER_EEVEE_NEXT":
            self.sample_count = scene.eevee.taa_render_samples


def update_resolution(self, context):
    if self.use_scene_resolution:
        scene = context.scene
        self.resolution_x = scene.render.resolution_x
        self.resolution_y = scene.render.resolution_y


class ExportSettings(bpy.types.PropertyGroup):
    use_scene_samples: bpy.props.BoolProperty(
        name="Use Scene Sample Count",
        description="If enabled, use the scene's sample count instead of custom value",
        default=False,
        update=update_sample_count,
    )

    sample_count: bpy.props.IntProperty(
        name="Sample Count",
        description="Custom sample count if not using scene value",
        default=128,
        min=1,
    )

    use_scene_resolution: bpy.props.BoolProperty(
        name="Use Scene Resolution",
        description="If enabled, use the scene's resolution instead of custom value",
        default=False,
        update=update_resolution,
    )

    resolution_x: bpy.props.IntProperty(
        name="Resolution X",
        description="Custom horizontal resolution if not using scene value",
        default=512,
        min=1,
        max=16384,
    )

    resolution_y: bpy.props.IntProperty(
        name="Resolution Y",
        description="Custom vertical resolution if not using scene value",
        default=512,
        min=1,
        max=16384,
    )

    integrator: bpy.props.EnumProperty(
        name="Integrator",
        items=[
            ("path_mis", "path_mis", ""),
            ("path_mats", "path_mats", ""),
            ("direct_ems", "direct_ems", ""),
            ("direct_mis", "direct_mis", ""),
            ("direct_mats", "direct_mats", ""),
            ("av", "Average Visibility", ""),
            ("material", "Material Preview", ""),
            ("normals", "Normals", ""),
        ],
        default="path_mis",
    )

    export_textures: bpy.props.BoolProperty(
        name="Export Textures",
        description="Export textures used by materials",
        default=False,
    )

    texture_format: bpy.props.EnumProperty(
        name="Texture Format",
        items=[
            ("PNG", "PNG", ""),
            ("JPEG", "JPEG", ""),
        ],
        default="PNG",
    )

    export_pointlights: bpy.props.BoolProperty(
        name="Export Point Lights",
        description="Export point lights in the scene",
        default=False,
    )

    reconstruction_filter: bpy.props.EnumProperty(
        name="Reconstruction Filter",
        items=[
            ("box", "Box", ""),
            ("gaussian", "Gaussian", ""),
            ("mitchell", "Mitchell-Netravali", ""),
            ("tent", "Tent", ""),
        ],
        default="gaussian",
    )


class Bento_Preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    # config file is in the same directory as this __init__.py
    path = os.path.dirname(__file__)
    config_path: bpy.props.StringProperty(
        name="Config Path",
        subtype="FILE_PATH",
        default=os.path.join(path, "config.toml"),
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Bento Prefrerences")
        layout.prop(self, "config_path")


class EXPORT_OT_nori(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.nori"
    bl_label = "Export Nori XML"
    bl_options = {"PRESET", "REGISTER", "UNDO"}

    filename_ext = ".xml"
    filter_glob: bpy.props.StringProperty(default="*.xml", options={"HIDDEN"})

    export_settings: bpy.props.PointerProperty(type=ExportSettings)

    def draw(self, context):
        layout = self.layout

        layout.label(text="Export Settings")

        # SPP
        use_scene_samples = self.export_settings.use_scene_samples
        layout.prop(self.export_settings, "use_scene_samples", icon="FILE_VOLUME")
        row = layout.row()
        row.enabled = not use_scene_samples
        row.prop(self.export_settings, "sample_count")

        # Resolution
        use_scene_resolution = self.export_settings.use_scene_resolution
        layout.prop(self.export_settings, "use_scene_resolution", icon="MOD_MULTIRES")
        row = layout.row()
        row.enabled = not use_scene_resolution
        row.prop(self.export_settings, "resolution_x")
        row.prop(self.export_settings, "resolution_y")

        # Integrator
        layout.prop(self.export_settings, "integrator", icon="SCENE")

        # Textures
        layout.prop(self.export_settings, "export_textures", icon="TEXTURE")
        row = layout.row()
        row.enabled = self.export_settings.export_textures
        row.prop(self.export_settings, "texture_format", icon="IMAGE_DATA")

        # Point Lights
        layout.prop(self.export_settings, "export_pointlights", icon="LIGHT")

        # Reconstruction Filter
        layout.prop(self.export_settings, "reconstruction_filter", icon="SMOOTHCURVE")

        # Camera warning
        no_cam = not context.scene.camera
        row = layout.row()
        if no_cam:
            row.label(text="No camera in the scene", icon="ERROR")

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, f"No export path specified. {self.filepath}")
            return {"CANCELLED"}

        if not context.scene.camera:
            self.report({"ERROR"}, "No camera found in the scene.")
            return {"CANCELLED"}

        config = load_config(bpy.context.preferences.addons[__name__].preferences)
        texture_dir = ""
        if self.export_settings.export_textures:
            texture_dir = os.path.join(os.path.dirname(self.filepath), "textures")
            os.makedirs(texture_dir, exist_ok=True)

        # Export materials
        materials = export_materials(config, texture_dir, self.export_settings)

        # Export meshes
        export_directory = os.path.dirname(self.filepath)
        mesh_data = export_meshes(context, export_directory)

        # Build XML
        root = ET.Element("scene")
        ET.SubElement(root, "integrator", type=self.export_settings.integrator)
        sampler_tag = ET.SubElement(root, "sampler", type="independent")
        ET.SubElement(
            sampler_tag,
            "integer",
            name="sampleCount",
            value=str(self.export_settings.sample_count),
        )
        camera = context.scene.camera
        camera_tag = create_camera_tag(camera, root, self.export_settings)

        # Create XML tags for each mesh
        for _, filepath, material in mesh_data:
            if material is None:
                # TODO: Assign a default material (diffuse)
                continue

            mat_xml = materials.get(material)
            mesh_xml = ET.SubElement(root, "mesh", type="obj")
            ET.SubElement(
                mesh_xml, "string", name="filename", value=f"meshes/{filepath}"
            )
            mesh_xml.append(mat_xml)

        # Export point lights
        if self.export_settings.export_pointlights:
            for obj in context.scene.objects:
                if obj.type == "LIGHT" and obj.data.type == "POINT":
                    light_tag = ET.SubElement(root, "emitter", type="point")
                    ET.SubElement(
                        light_tag,
                        "point",
                        name="position",
                        value=" ".join([str(round(v, 4)) for v in obj.location]),
                    )
                    color = obj.data.color
                    strength = obj.data.energy
                    strength *= 1 if obj.data.normalize else 4
                    radiance = [c * strength for c in color[:3]]
                    ET.SubElement(
                        light_tag,
                        "color",
                        name="power",
                        value=convert_values(radiance, "color"),
                    )

        tree = ET.ElementTree(root)
        tree.write(self.filepath, encoding="utf-8", xml_declaration=True)
        print(f"Exported scene to {self.filepath}")

        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


def create_camera_tag(camera, root, export_settings):
    camera_tag = ET.SubElement(root, "camera", type="perspective")
    ET.SubElement(
        camera_tag,
        "float",
        name="fov",
        value=str(camera.data.angle * (180.0 / 3.14159265)),
    )
    ET.SubElement(
        camera_tag,
        "integer",
        name="width",
        value=str(export_settings.resolution_x),
    )
    ET.SubElement(
        camera_tag,
        "integer",
        name="height",
        value=str(export_settings.resolution_y),
    )
    transform = ET.SubElement(
        camera_tag,
        "transform",
        name="toWorld",
    )
    ET.SubElement(
        transform,
        "scale",
        value="1 1 -1",
    )
    ET.SubElement(
        transform,
        "matrix",
        value=" ".join([str(round(v, 6)) for row in camera.matrix_world for v in row]),
    )
    ET.SubElement(
        camera_tag,
        "rfilter",
        type=export_settings.reconstruction_filter,
    )
    return camera_tag


def menu_func_export(self, context):
    self.layout.operator(
        EXPORT_OT_nori.bl_idname,
        text="Nori (.xml)",
    )


classes_to_register = [
    ExportSettings,
    EXPORT_OT_nori,
    Bento_Preferences,
]


def register():
    for cls in classes_to_register:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    for cls in reversed(classes_to_register):
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()

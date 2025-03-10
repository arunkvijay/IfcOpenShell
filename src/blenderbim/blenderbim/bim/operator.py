# BlenderBIM Add-on - OpenBIM Blender Add-on
# Copyright (C) 2020, 2021 Dion Moult <dion@thinkmoult.com>
#
# This file is part of BlenderBIM Add-on.
#
# BlenderBIM Add-on is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BlenderBIM Add-on is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BlenderBIM Add-on.  If not, see <http://www.gnu.org/licenses/>.

import os
import bpy
import json
import time
import logging
import textwrap
import shutil
import platform
import subprocess
import tempfile
import webbrowser
import ifcopenshell
import blenderbim.bim.handler
import blenderbim.tool as tool
from . import schema
from blenderbim.bim import import_ifc
from blenderbim.bim.ifc import IfcStore
from blenderbim.bim.prop import StrProperty
from blenderbim.bim.ui import IFCFileSelector
from blenderbim.bim.helper import get_enum_items
from mathutils import Vector, Matrix, Euler
from math import radians


class SwitchTab(bpy.types.Operator):
    bl_idname = "bim.switch_tab"
    bl_label = "Switch Tab"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Switches to the last used tab"

    def execute(self, context):
        if context.area.spaces.active.search_filter:
            return {"FINISHED"}
        aprops = context.screen.BIMAreaProperties[context.screen.areas[:].index(context.area)]
        aprops.tab = aprops.alt_tab
        return {"FINISHED"}


class OpenUri(bpy.types.Operator):
    bl_idname = "bim.open_uri"
    bl_label = "Open URI"
    uri: bpy.props.StringProperty()

    def execute(self, context):
        webbrowser.open(self.uri)
        return {"FINISHED"}


class SelectURIAttribute(bpy.types.Operator):
    bl_idname = "bim.select_uri_attribute"
    bl_label = "Select URI Attribute"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select a local file"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    data_path: bpy.props.StringProperty(name="Data Path")
    use_relative_path: bpy.props.BoolProperty(name="Use Relative Path", default=False)

    def execute(self, context):
        # data_path contains the latter half of the path to the string_value property
        # I have no idea how to find out the former half, so let's just use brute force.
        data_path = self.data_path.replace(".string_value", "")
        attribute = None
        try:
            attribute = eval(f"bpy.context.scene.{data_path}")
        except:
            try:
                attribute = eval(f"bpy.context.active_object.{data_path}")
            except:
                try:
                    attribute = eval(f"bpy.context.active_object.active_material.{data_path}")
                except:
                    # Do you know a better way?
                    pass
        if attribute:
            filepath = self.filepath
            if self.use_relative_path:
                filepath = os.path.relpath(filepath, os.path.dirname(tool.Ifc.get_path()))
            attribute.string_value = filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class SelectIfcFile(bpy.types.Operator, IFCFileSelector):
    bl_idname = "bim.select_ifc_file"
    bl_label = "Select IFC File"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select a different IFC file"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.ifc;*.ifczip;*.ifcxml", options={"HIDDEN"})
    use_relative_path: bpy.props.BoolProperty(name="Use Relative Path", default=False)

    def execute(self, context):
        if self.is_existing_ifc_file():
            context.scene.BIMProperties.ifc_file = self.get_filepath()
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class ReloadSelectedIfcFile(bpy.types.Operator):
    bl_idname = "bim.reload_selected_ifc_file"
    bl_label = "Reload selected IFC File"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Reload currently selected IFC file"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        filepath = context.scene.BIMProperties.ifc_file
        valid_file = os.path.exists(filepath) and "ifc" in os.path.splitext(filepath)[1].lower()
        if not valid_file:
            self.report({"ERROR"}, f"Couldn't find .ifc file by the path '{filepath}'")
            return {"ERROR"}
        context.scene.BIMProperties.ifc_file = context.scene.BIMProperties.ifc_file
        return {"FINISHED"}


class SelectDataDir(bpy.types.Operator):
    bl_idname = "bim.select_data_dir"
    bl_label = "Select Data Directory"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select the directory that contains all IFC data es. PSet, styles, etc..."
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        context.scene.BIMProperties.data_dir = os.path.dirname(self.filepath)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class SelectSchemaDir(bpy.types.Operator):
    bl_idname = "bim.select_schema_dir"
    bl_label = "Select Schema Directory"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select the directory containing the IFC schema specification"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        context.scene.BIMProperties.schema_dir = os.path.dirname(self.filepath)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class FileAssociate(bpy.types.Operator):
    bl_idname = "bim.file_associate"
    bl_label = "Associate BlenderBIM with *.ifc files"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Creates a Desktop launcher and associates it with IFC files"

    @classmethod
    def poll(cls, context):
        if platform.system() == "Linux":
            return True
        cls.poll_message_set("Option available only on Linux.")
        # TODO Windows and Darwin
        # https://stackoverflow.com/questions/1082889/how-to-change-filetype-association-in-the-registry
        return False

    def execute(self, context):
        src_dir = os.path.join(os.path.dirname(__file__), "../libs/desktop")
        binary_path = bpy.app.binary_path
        if platform.system() == "Linux":
            destdir = os.path.join(os.environ["HOME"], ".local")
            self.install_desktop_linux(src_dir=src_dir, destdir=destdir, binary_path=binary_path)
        return {"FINISHED"}

    def install_desktop_linux(self, src_dir=None, destdir="/tmp", binary_path="/usr/bin/blender"):
        """Creates linux file assocations and launcher icon"""

        for rel_path in (
            "bin",
            "share/icons/hicolor/128x128/apps",
            "share/icons/hicolor/128x128/mimetypes",
            "share/applications",
            "share/mime/packages",
        ):
            os.makedirs(os.path.join(destdir, rel_path), exist_ok=True)

        shutil.copy(
            os.path.join(src_dir, "blenderbim.png"),
            os.path.join(destdir, "share/icons/hicolor/128x128/apps"),
        )
        shutil.copy(
            os.path.join(src_dir, "blenderbim.desktop"),
            os.path.join(destdir, "share/applications"),
        )
        shutil.copy(
            os.path.join(src_dir, "blenderbim.xml"),
            os.path.join(destdir, "share/mime/packages"),
        )
        shutil.copyfile(
            os.path.join(src_dir, "x-ifc_128x128.png"),
            os.path.join(destdir, "share/icons/hicolor/128x128/mimetypes", "x-ifc.png"),
        )

        # copy and rewrite wrapper script
        with open(os.path.join(src_dir, "blenderbim"), "r") as wrapper_template:
            filedata = wrapper_template.read()
            filedata = filedata.replace("#BLENDER_EXE=/opt/blender-3.3/blender", 'BLENDER_EXE="' + binary_path + '"')
        with open(os.path.join(destdir, "bin", "blenderbim"), "w") as wrapper:
            wrapper.write(filedata)

        os.chmod(os.path.join(destdir, "bin", "blenderbim"), 0o755)

        self.refresh_system_linux(destdir=destdir)

    def refresh_system_linux(self, destdir="/tmp"):
        """Attempt to update mime and desktop databases"""
        try:
            subprocess.call(["update-mime-database", os.path.join(destdir, "share/mime")])
        except:
            pass
        try:
            subprocess.call(["update-desktop-database", os.path.join(destdir, "share/applications")])
        except:
            pass


class FileUnassociate(bpy.types.Operator):
    bl_idname = "bim.file_unassociate"
    bl_label = "Remove BlenderBIM *.ifc association"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Removes Desktop launcher and unassociates it with IFC files"

    @classmethod
    def poll(cls, context):
        if platform.system() == "Linux":
            return True
        cls.poll_message_set("Option available only on Linux.")
        return False

    def execute(self, context):
        if platform.system() == "Linux":
            destdir = os.path.join(os.environ["HOME"], ".local")
            self.uninstall_desktop_linux(destdir=destdir)
        return {"FINISHED"}

    def uninstall_desktop_linux(self, destdir="/tmp"):
        """Removes linux file assocations and launcher icon"""
        for rel_path in (
            "share/icons/hicolor/128x128/apps/blenderbim.png",
            "share/icons/hicolor/128x128/mimetypes/x-ifc.png",
            "share/applications/blenderbim.desktop",
            "share/mime/packages/blenderbim.xml",
            "bin/blenderbim",
        ):
            try:
                os.remove(os.path.join(destdir, rel_path))
            except:
                pass

        self.refresh_system_linux(destdir=destdir)

    def refresh_system_linux(self, destdir="/tmp"):
        """Attempt to update mime and desktop databases"""
        try:
            subprocess.call(["update-mime-database", os.path.join(destdir, "share/mime")])
        except:
            pass
        try:
            subprocess.call(["update-desktop-database", os.path.join(destdir, "share/applications")])
        except:
            pass


class OpenUpstream(bpy.types.Operator):
    bl_idname = "bim.open_upstream"
    bl_label = "Open Upstream Reference"
    page: bpy.props.StringProperty()

    def execute(self, context):
        if self.page == "home":
            webbrowser.open("https://blenderbim.org/")
        elif self.page == "docs":
            webbrowser.open("https://blenderbim.org/docs/")
        elif self.page == "wiki":
            webbrowser.open("https://wiki.osarch.org/index.php?title=Category:BlenderBIM_Add-on")
        elif self.page == "community":
            webbrowser.open("https://community.osarch.org/")
        elif self.page == "fund":
            webbrowser.open("https://opencollective.com/opensourcebim")
        return {"FINISHED"}


class BIM_OT_add_section_plane(bpy.types.Operator):
    """Add a temporary empty object as a section cutaway. Cull all geometry rendering below the empty's local Z axis"""

    bl_idname = "bim.add_section_plane"
    bl_label = "Add Temporary Section Cutaway"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = self.create_section_obj(context)
        if not self.has_section_override_node():
            self.create_section_compare_node()
            self.create_section_override_node(obj, context)
        else:
            self.append_obj_to_section_override_node(obj)
        self.add_default_material_if_none_exists(context)
        self.override_materials()
        return {"FINISHED"}

    def create_section_obj(self, context):
        section = bpy.data.objects.new("Section", None)
        section.empty_display_type = "SINGLE_ARROW"
        section.empty_display_size = 5
        section.show_in_front = True
        if (
            context.active_object
            and context.active_object.select_get()
            and isinstance(context.active_object.data, bpy.types.Camera)
        ):
            section.matrix_world = (
                context.active_object.matrix_world @ Euler((radians(180.0), 0.0, 0.0), "XYZ").to_matrix().to_4x4()
            )
        else:
            section.rotation_euler = Euler((radians(180.0), 0.0, 0.0), "XYZ")
            section.location = context.scene.cursor.location
        collection = bpy.data.collections.get("Sections")
        if not collection:
            collection = bpy.data.collections.new("Sections")
            context.scene.collection.children.link(collection)
        collection.objects.link(section)
        return section

    def has_section_override_node(self):
        return bpy.data.node_groups.get("Section Override")

    def create_section_compare_node(self):
        group = bpy.data.node_groups.new("Section Compare", type="ShaderNodeTree")
        group.inputs.new("NodeSocketFloat", "Value")
        group.inputs["Value"].default_value = 1.0  # Mandatory multiplier for the last node group
        group.inputs.new("NodeSocketVector", "Vector")
        group.outputs.new("NodeSocketFloat", "Value")
        group.outputs.new("NodeSocketFloat", "Line Decorator")
        group_input = group.nodes.new(type="NodeGroupInput")
        group_input.location = 0, 50

        separate_xyz = group.nodes.new(type="ShaderNodeSeparateXYZ")
        separate_xyz.location = 200, 0

        greater = group.nodes.new(type="ShaderNodeMath")
        greater.operation = "GREATER_THAN"
        greater.inputs[1].default_value = 0
        greater.location = 400, 0

        compare = group.nodes.new(type="ShaderNodeMath")
        compare.operation = "COMPARE"
        compare.inputs[1].default_value = 0
        compare.inputs[2].default_value = 0.04
        compare.location = 400, -200

        multiply = group.nodes.new(type="ShaderNodeMath")
        multiply.operation = "MULTIPLY"
        multiply.inputs[0].default_value = 1
        multiply.location = 600, 150

        group_output = group.nodes.new(type="NodeGroupOutput")
        group_output.location = 800, 0

        group.links.new(group_input.outputs["Value"], multiply.inputs[0])
        group.links.new(group_input.outputs["Vector"], separate_xyz.inputs[0])
        group.links.new(separate_xyz.outputs[2], greater.inputs[0])
        group.links.new(greater.outputs[0], multiply.inputs[1])
        group.links.new(multiply.outputs[0], group_output.inputs["Value"])
        group.links.new(separate_xyz.outputs[2], compare.inputs[0])
        group.links.new(compare.outputs[0], group_output.inputs["Line Decorator"])

    def create_section_override_node(self, obj, context):
        group = bpy.data.node_groups.new("Section Override", type="ShaderNodeTree")
        group.inputs.new("NodeSocketShader", "Shader")
        group.outputs.new("NodeSocketShader", "Shader")
        links = group.links
        nodes = group.nodes

        group_input = nodes.new(type="NodeGroupInput")
        group_output = nodes.new(type="NodeGroupOutput")
        group_output.location = 800, 250

        mix_decorator = group.nodes.new(type="ShaderNodeMixShader")
        mix_decorator.name = "Line Decorator Mix"
        mix_decorator.location = group_output.location - Vector((200, 0))

        mix_section = group.nodes.new(type="ShaderNodeMixShader")
        mix_section.name = "Section Mix"
        mix_section.inputs[0].default_value = 1  # Directly pass input shader when there is no cutaway
        mix_section.location = mix_decorator.location - Vector((200, 200))

        transparent = nodes.new(type="ShaderNodeBsdfTransparent")
        transparent.location = mix_section.location - Vector((200, 100))

        mix_backfacing = nodes.new(type="ShaderNodeMixShader")
        mix_backfacing.location = mix_section.location - Vector((200, 0))

        group_input.location = mix_backfacing.location - Vector((200, 50))

        backfacing = nodes.new(type="ShaderNodeNewGeometry")
        backfacing.location = mix_backfacing.location + Vector((-200, 200))

        emission = nodes.new(type="ShaderNodeEmission")
        emission.inputs[0].default_value = list(context.scene.BIMProperties.section_plane_colour) + [1]
        emission.location = mix_backfacing.location - Vector((200, 150))

        cut_obj = nodes.new(type="ShaderNodeTexCoord")
        cut_obj.object = obj
        cut_obj.location = backfacing.location - Vector((200, 200))

        section_compare = nodes.new(type="ShaderNodeGroup")
        section_compare.node_tree = bpy.data.node_groups.get("Section Compare")
        section_compare.name = "Last Section Compare"
        section_compare.location = backfacing.location + Vector((0, 200))

        links.new(cut_obj.outputs["Object"], section_compare.inputs[1])
        links.new(backfacing.outputs["Backfacing"], mix_backfacing.inputs[0])
        links.new(group_input.outputs["Shader"], mix_backfacing.inputs[1])
        links.new(emission.outputs["Emission"], mix_backfacing.inputs[2])
        links.new(section_compare.outputs["Value"], mix_section.inputs[0])
        links.new(transparent.outputs[0], mix_section.inputs[1])
        links.new(mix_backfacing.outputs["Shader"], mix_section.inputs[2])
        links.new(section_compare.outputs["Line Decorator"], mix_decorator.inputs[0])
        links.new(mix_section.outputs["Shader"], mix_decorator.inputs[1])
        links.new(mix_decorator.outputs["Shader"], group_output.inputs["Shader"])

    def append_obj_to_section_override_node(self, obj):
        group = bpy.data.node_groups.get("Section Override")
        try:
            last_section_node = next(
                n
                for n in group.nodes
                if isinstance(n, bpy.types.ShaderNodeGroup)
                and n.node_tree.name == "Section Compare"
                and not n.inputs[0].links
            )
            offset = Vector((0, 0))
        except StopIteration:
            last_section_node = group.nodes.get("Section Mix")
            offset = Vector((200, 0))
        section_compare = group.nodes.new(type="ShaderNodeGroup")
        section_compare.node_tree = bpy.data.node_groups.get("Section Compare")
        section_compare.location = last_section_node.location - Vector((200, 0)) - offset

        cut_obj = group.nodes.new(type="ShaderNodeTexCoord")
        cut_obj.object = obj
        cut_obj.location = last_section_node.location - Vector((400, 150)) - offset

        group.links.new(section_compare.outputs[0], last_section_node.inputs[0])
        group.links.new(cut_obj.outputs["Object"], section_compare.inputs[1])

        section_compare.name = "Last Section Compare"

    def add_default_material_if_none_exists(self, context):
        material = bpy.data.materials.get("Section Override")
        if not material:
            material = bpy.data.materials.new("Section Override")
            material.use_nodes = True

        if context.scene.BIMProperties.should_section_selected_objects:
            objects = list(context.selected_objects)
        else:
            objects = list(context.visible_objects)

        for obj in objects:
            aggregate = obj.instance_collection
            if aggregate and "IfcRelAggregates/" in aggregate.name:
                for part in aggregate.objects:
                    objects.append(part)
            if not (obj.data and hasattr(obj.data, "materials") and obj.data.materials and obj.data.materials[0]):
                if obj.data and hasattr(obj.data, "materials"):
                    if len(obj.material_slots):
                        obj.material_slots[0].material = material
                    else:
                        obj.data.materials.append(material)

    def override_materials(self):
        override = bpy.data.node_groups.get("Section Override")
        for material in bpy.data.materials:
            material.use_nodes = True
            if material.node_tree.nodes.get("Section Override"):
                continue
            material.blend_method = "HASHED"
            material.shadow_method = "HASHED"
            material_output = tool.Blender.get_material_node(material, "OUTPUT_MATERIAL", {"is_active_output": True})
            if not material_output:
                continue
            from_socket = material_output.inputs[0].links[0].from_socket
            section_override = material.node_tree.nodes.new(type="ShaderNodeGroup")
            section_override.name = "Section Override"
            section_override.node_tree = override
            material.node_tree.links.new(from_socket, section_override.inputs[0])
            material.node_tree.links.new(section_override.outputs[0], material_output.inputs[0])


class BIM_OT_remove_section_plane(bpy.types.Operator):
    """Remove selected section plane. No effect if executed on a regular object"""

    bl_idname = "bim.remove_section_plane"
    bl_label = "Remove Temporary Section Cutaway"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object and bpy.data.node_groups.get("Section Override")

    def execute(self, context):
        name = context.active_object.name
        section_override = bpy.data.node_groups.get("Section Override")
        tex_coords = next(
            (
                n
                for n in section_override.nodes
                if isinstance(n, bpy.types.ShaderNodeTexCoord) and n.object.name == name
            ),
            None,
        )
        if tex_coords is not None:
            section_compare = tex_coords.outputs["Object"].links[0].to_node
            if section_compare.inputs[0].links:
                previous_section_compare = section_compare.inputs[0].links[0].from_node
                next_section_compare = section_compare.outputs[0].links[0].to_node
                section_override.links.new(previous_section_compare.outputs[0], next_section_compare.inputs[0])
                self.offset_previous_nodes(section_compare, offset_x=200)
            section_override.nodes.remove(section_compare)
            section_override.nodes.remove(tex_coords)
            bpy.data.objects.remove(context.active_object)

        return {"FINISHED"}

    def offset_previous_nodes(self, section_compare, offset_x=0, offset_y=0):
        if section_compare.inputs[0].links:
            previous_section_compare = section_compare.inputs[0].links[0].from_node
            previous_section_compare.location += Vector((offset_x, offset_y))
            if previous_section_compare.inputs[1].links:
                previous_section_compare.inputs[1].links[0].from_node.location += Vector((offset_x, offset_y))
            self.offset_previous_nodes(previous_section_compare, offset_x, offset_y)

    def purge_all_section_data(self, context):
        bpy.data.materials.remove(bpy.data.materials.get("Section Override"))
        for material in bpy.data.materials:
            if not material.node_tree:
                continue
            override = material.node_tree.nodes.get("Section Override")
            if not override:
                continue
            material.node_tree.links.new(
                override.inputs[0].links[0].from_socket, override.outputs[0].links[0].to_socket
            )
            material.node_tree.nodes.remove(override)
        bpy.data.node_groups.remove(bpy.data.node_groups.get("Section Override"))
        bpy.data.node_groups.remove(bpy.data.node_groups.get("Section Compare"))
        bpy.ops.object.delete({"selected_objects": [context.active_object]})


class ReloadIfcFile(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.reload_ifc_file"
    bl_label = "Reload IFC File"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Reload an updated IFC file"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.ifc", options={"HIDDEN"})

    def _execute(self, context):
        import ifcdiff

        old = tool.Ifc.get()
        new = ifcopenshell.open(self.filepath)

        ifc_diff = ifcdiff.IfcDiff(old, new, relationships=[])
        ifc_diff.diff()

        changed_elements = set([k for k, v in ifc_diff.change_register.items() if "geometry_changed" in v])

        for global_id in ifc_diff.deleted_elements | changed_elements:
            element = tool.Ifc.get().by_guid(global_id)
            obj = tool.Ifc.get_object(element)
            if obj:
                bpy.data.objects.remove(obj)

        # STEP IDs may change, but we assume the GlobalID to be constant
        obj_map = {}
        for obj in bpy.data.objects:
            element = tool.Ifc.get_entity(obj)
            if element and hasattr(element, "GlobalId"):
                obj_map[obj.name] = element.GlobalId

        delta_elements = [new.by_guid(global_id) for global_id in ifc_diff.added_elements | changed_elements]
        tool.Ifc.set(new)

        for obj in bpy.data.objects:
            global_id = obj_map.get(obj.name)
            if global_id:
                try:
                    tool.Ifc.link(new.by_guid(global_id), obj)
                except:
                    # Still prototyping, so things like types definitely won't work
                    print("Could not relink", obj)

        start = time.time()
        logger = logging.getLogger("ImportIFC")
        path_log = os.path.join(context.scene.BIMProperties.data_dir, "process.log")
        if not os.access(context.scene.BIMProperties.data_dir, os.W_OK):
            path_log = os.path.join(tempfile.mkdtemp(), "process.log")
        logging.basicConfig(
            filename=path_log,
            filemode="a",
            level=logging.DEBUG,
        )
        settings = import_ifc.IfcImportSettings.factory(context, self.filepath, logger)
        settings.has_filter = True
        settings.should_filter_spatial_elements = False
        settings.elements = delta_elements
        settings.logger.info("Starting import")
        ifc_importer = import_ifc.IfcImporter(settings)
        ifc_importer.execute()
        settings.logger.info("Import finished in {:.2f} seconds".format(time.time() - start))
        print("Import finished in {:.2f} seconds".format(time.time() - start))

        context.scene.BIMProperties.ifc_file = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class AddIfcFile(bpy.types.Operator):
    bl_idname = "bim.add_ifc_file"
    bl_label = "Add IFC File"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.DocProperties.ifc_files.add()
        return {"FINISHED"}


class RemoveIfcFile(bpy.types.Operator):
    bl_idname = "bim.remove_ifc_file"
    bl_label = "Remove IFC File"
    index: bpy.props.IntProperty()
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.DocProperties.ifc_files.remove(self.index)
        return {"FINISHED"}


class BIM_OT_open_webbrowser(bpy.types.Operator):
    bl_idname = "bim.open_webbrowser"
    bl_description = "Open the URL in your Web Browser"
    bl_label = "Open URL"

    url: bpy.props.StringProperty()

    def execute(self, context):
        import webbrowser

        webbrowser.open(self.url)
        return {"FINISHED"}


class SelectExternalMaterialDir(bpy.types.Operator):
    bl_idname = "bim.select_external_material_dir"
    bl_label = "Select Material File"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        # TODO: this is dead code, awaiting reimplementation. See #1222.
        context.active_object.active_material.BIMMaterialProperties.location = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class FetchExternalMaterial(bpy.types.Operator):
    bl_idname = "bim.fetch_external_material"
    bl_label = "Fetch External Material"

    def execute(self, context):
        # TODO: this is dead code, awaiting reimplementation. See #1222.
        location = context.active_object.active_material.BIMMaterialProperties.location
        if location[-6:] != ".mpass":
            return {"FINISHED"}
        if not os.path.isabs(location):
            location = os.path.join(context.scene.BIMProperties.data_dir, location)
        with open(location) as f:
            self.material_pass = json.load(f)
        if context.scene.render.engine == "BLENDER_EEVEE" and "eevee" in self.material_pass:
            self.fetch_eevee_or_cycles("eevee", context)
        elif context.scene.render.engine == "CYCLES" and "cycles" in self.material_pass:
            self.fetch_eevee_or_cycles("cycles", context)
        return {"FINISHED"}

    def fetch_eevee_or_cycles(self, name, context):
        identification = context.active_object.active_material.BIMMaterialProperties.identification
        uri = self.material_pass[name]["uri"]
        if not os.path.isabs(uri):
            uri = os.path.join(context.scene.BIMProperties.data_dir, uri)
        bpy.ops.wm.link(filename=identification, directory=os.path.join(uri, "Material"))
        for material in bpy.data.materials:
            if material.name == identification and material.library:
                context.active_object.material_slots[0].material = material
                return


class FetchObjectPassport(bpy.types.Operator):
    bl_idname = "bim.fetch_object_passport"
    bl_label = "Fetch Object Passport"

    def execute(self, context):
        # TODO: this is dead code, awaiting reimplementation. See #1222.
        for reference in context.active_object.BIMObjectProperties.document_references:
            reference = context.scene.BIMProperties.document_references[reference.name]
            if reference.location[-6:] == ".blend":
                self.fetch_blender(reference, context)
        return {"FINISHED"}

    def fetch_blender(self, reference, context):
        bpy.ops.wm.link(filename=reference.name, directory=os.path.join(reference.location, "Mesh"))
        context.active_object.data = bpy.data.meshes[reference.name]


class ConfigureVisibility(bpy.types.Operator):
    bl_idname = "bim.configure_visibility"
    bl_label = "Configure module UI visibility in BlenderBIM"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        from blenderbim.bim import modules

        wm = context.window_manager
        if not len(context.scene.BIMProperties.module_visibility):
            for module in sorted(modules.keys()):
                new = context.scene.BIMProperties.module_visibility.add()
                new.name = module
        return wm.invoke_props_dialog(self, width=450)

    def draw(self, context):
        layout = self.layout

        layout.prop(context.scene.BIMProperties, "ui_preset")
        layout.separator()
        layout.label(text="Adjust the modules to your liking:")

        grid = layout.column_flow(columns=3)
        for module in context.scene.BIMProperties.module_visibility:
            split = grid.split()
            col = split.column()
            col.label(text=module.name.capitalize())

            col = split.column()
            col.prop(module, "is_visible", text="")

    def execute(self, context):
        return {"FINISHED"}


def update_enum_property_search_prop(self, context):
    for i, prop in enumerate(self.collection_names):
        if prop.name == self.dummy_name:
            setattr(context.data, self.prop_name, self.collection_identifiers[i].name)
            predefined_type = self.collection_predefined_types[i].name
            if predefined_type:
                try:
                    setattr(context.data, "ifc_predefined_type", predefined_type)
                except TypeError:  # User clicked on a suggestion, but it's not a predefined type
                    pass
            break


class BIM_OT_enum_property_search(bpy.types.Operator):
    bl_idname = "bim.enum_property_search"
    bl_label = "Search For Property"
    bl_options = {"REGISTER", "UNDO"}
    dummy_name: bpy.props.StringProperty(name="Property", update=update_enum_property_search_prop)
    collection_names: bpy.props.CollectionProperty(type=StrProperty)
    collection_identifiers: bpy.props.CollectionProperty(type=StrProperty)
    collection_predefined_types: bpy.props.CollectionProperty(type=StrProperty)
    prop_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        self.clear_collections()
        self.data = context.data
        items = get_enum_items(self.data, self.prop_name, context)
        if items is None:
            return {"FINISHED"}
        self.add_items_regular(items)
        self.add_items_suggestions()
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        # Mandatory to access context.data in update :
        self.layout.context_pointer_set(name="data", data=self.data)
        self.layout.prop_search(self, "dummy_name", self, "collection_names")

    def execute(self, context):
        return {"FINISHED"}

    def clear_collections(self):
        self.collection_names.clear()
        self.collection_identifiers.clear()

    def add_item(self, identifier: str, name: str, predefined_type: str = ""):
        self.collection_identifiers.add().name = identifier
        self.collection_names.add().name = name
        self.collection_predefined_types.add().name = predefined_type

    def add_items_regular(self, items):
        self.identifiers = []
        for item in items:
            self.identifiers.append(item[0])
            self.add_item(identifier=item[0], name=item[1])
            if item[0] == getattr(self.data, self.prop_name):
                self.dummy_name = item[1]  # We found the current enum name

    def add_items_suggestions(self):
        getter_suggestions = getattr(self.data, "getter_enum_suggestions", None)
        if getter_suggestions is not None:
            mapping = getter_suggestions.get(self.prop_name)
            if mapping is None:
                return
            for key, values in mapping().items():
                if key in self.identifiers:
                    if not isinstance(values, (tuple, list)):
                        values = [values]
                    for value in values:
                        self.add_item(identifier=key, name=key + " > " + value, predefined_type=value.upper())


class EditBlenderCollection(bpy.types.Operator):
    bl_idname = "bim.edit_blender_collection"
    bl_label = "Add or Remove Blender Collection Item"
    bl_options = {"REGISTER", "UNDO"}
    option: bpy.props.StringProperty(description="add or remove item from collection")
    collection: bpy.props.StringProperty(description="collection to be edited")
    index: bpy.props.IntProperty(description="index of item to be removed")

    def execute(self, context):
        if self.option == "add":
            getattr(context.bim_prop_group, self.collection).add()
        else:
            getattr(context.bim_prop_group, self.collection).remove(self.index)
        return {"FINISHED"}


class BIM_OT_show_description(bpy.types.Operator):
    bl_idname = "bim.show_description"
    bl_label = "Description"
    attr_name: bpy.props.StringProperty()
    description: bpy.props.StringProperty()
    url: bpy.props.StringProperty()

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=450)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        wrapper = textwrap.TextWrapper(width=80)
        for line in wrapper.wrap(self.attr_name + " : " + self.description):
            layout.label(text=line)
        if self.url:
            url_op = layout.operator("bim.open_webbrowser", icon="URL", text="Online IFC Documentation")
            url_op.url = self.url

    @classmethod
    def description(cls, context, properties):
        return properties.description

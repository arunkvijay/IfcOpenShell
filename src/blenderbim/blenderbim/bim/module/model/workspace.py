# BlenderBIM Add-on - OpenBIM Blender Add-on
# Copyright (C) 2020, 2021, 2022 Dion Moult <dion@thinkmoult.com>
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
import ifcopenshell
import ifcopenshell.util.unit
import blenderbim.tool as tool
import blenderbim.bim.module.type.prop as type_prop
from blenderbim.bim.helper import prop_with_search, close_operator_panel
from bpy.types import WorkSpaceTool
from blenderbim.bim.module.model.data import AuthoringData, RailingData, RoofData
from blenderbim.bim.module.drawing.data import DecoratorData
from blenderbim.bim.module.model.prop import get_ifc_class


class BimTool(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"

    bl_idname = "bim.bim_tool"
    bl_label = "BIM Tool"
    bl_description = "Gives you BIM authoring related superpowers"
    bl_icon = os.path.join(os.path.dirname(__file__), "ops.authoring.bim")
    bl_widget = None
    bl_keymap = tool.Blender.get_default_selection_keypmap() + (
        # ("bim.wall_tool_op", {"type": 'MOUSEMOVE', "value": 'ANY'}, {"properties": []}),
        # ("mesh.add_wall", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {"properties": []}),
        # ("bim.sync_modeling", {"type": 'MOUSEMOVE', "value": 'ANY'}, {"properties": []}),
        ("bim.hotkey", {"type": "A", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_A")]}),
        ("bim.hotkey", {"type": "B", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_B")]}),
        ("bim.hotkey", {"type": "C", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_C")]}),
        ("bim.hotkey", {"type": "E", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_E")]}),
        ("bim.hotkey", {"type": "F", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_F")]}),
        ("bim.hotkey", {"type": "G", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_G")]}),
        ("bim.hotkey", {"type": "K", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_K")]}),
        ("bim.hotkey", {"type": "M", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_M")]}),
        ("bim.hotkey", {"type": "O", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_O")]}),
        ("bim.hotkey", {"type": "Q", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_Q")]}),
        ("bim.hotkey", {"type": "R", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_R")]}),
        ("bim.hotkey", {"type": "T", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_T")]}),
        ("bim.hotkey", {"type": "V", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_V")]}),
        ("bim.hotkey", {"type": "X", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_X")]}),
        ("bim.hotkey", {"type": "Y", "value": "PRESS", "shift": True}, {"properties": [("hotkey", "S_Y")]}),
        ("bim.hotkey", {"type": "D", "value": "PRESS", "alt": True}, {"properties": [("hotkey", "A_D")]}),
        ("bim.hotkey", {"type": "E", "value": "PRESS", "alt": True}, {"properties": [("hotkey", "A_E")]}),
        ("bim.hotkey", {"type": "O", "value": "PRESS", "alt": True}, {"properties": [("hotkey", "A_O")]}),
        ("bim.hotkey", {"type": "P", "value": "PRESS", "ctrl": True}, {"properties": [("hotkey", "C_P")]}),
        ("bim.hotkey", {"type": "P", "value": "PRESS", "alt": True}, {"properties": [("hotkey", "A_P")]}),
    )

    def draw_settings(context, layout, ws_tool):
        # Unlike operators, Blender doesn't treat workspace tools as a class, so we'll create our own.
        BimToolUI.draw(context, layout)


def add_layout_hotkey_operator(layout, text, hotkey, description):
    modifiers = {
        "A": "EVENT_ALT",
        "S": "EVENT_SHIFT",
    }
    modifier, key = hotkey.split("_")

    row = layout.row(align=True)
    row.label(text="", icon=modifiers[modifier])
    row.label(text="", icon=f"EVENT_{key}")

    op = row.operator("bim.hotkey", text=text)
    op.hotkey = hotkey
    op.description = description
    return op


class BimToolUI:
    @classmethod
    def draw(cls, context, layout):
        cls.layout = layout
        cls.props = context.scene.BIMModelProperties

        row = cls.layout.row(align=True)
        if not tool.Ifc.get():
            row.label(text="No IFC Project", icon="ERROR")
            return

        if not AuthoringData.is_loaded:
            AuthoringData.load()

        if context.region.type == "TOOL_HEADER":
            cls.draw_header_interface()
        elif context.region.type in ("UI", "WINDOW"):
            # same interface for both n-panel sidebar and object properties
            cls.draw_basic_bim_tool_interface()

        if context.active_object and context.selected_objects:
            cls.draw_edit_object_interface(context)
        elif not context.selected_objects:
            cls.draw_create_object_interface()

    @classmethod
    def draw_create_object_interface(cls):
        if not AuthoringData.data["relating_type_id"]:
            return
        if cls.props.ifc_class == "IfcWallType":
            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="rl1", text="RL")

            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="extrusion_depth", text="Height")

            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="length", text="Length")

            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="x_angle", text="X Angle")
        elif cls.props.ifc_class in ("IfcSlabType", "IfcRampType", "IfcRoofType"):
            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="x_angle", text="X Angle")
        elif cls.props.ifc_class in ("IfcColumnType", "IfcBeamType", "IfcMemberType"):
            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="cardinal_point", text="Axis")

            row = cls.layout.row(align=True)
            label = "Height" if cls.props.ifc_class == "IfcColumn" else "Length"
            row.prop(data=cls.props, property="extrusion_depth", text=label)
        elif cls.props.ifc_class in ("IfcDoorType", "IfcDoorStyle"):
            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="rl1", text="RL")
        elif cls.props.ifc_class in ("IfcWindowType", "IfcWindowStyle", "IfcDoorType", "IfcDoorStyle"):
            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="rl2", text="RL")
        elif cls.props.ifc_class in ("IfcSpaceType"):
            add_layout_hotkey_operator(cls.layout, "Generate", "S_G", bpy.ops.bim.generate_space.__doc__)

    @classmethod
    def draw_edit_object_interface(cls, context):
        if AuthoringData.data["active_material_usage"] == "LAYER2":
            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="extrusion_depth", text="Height")
            op = row.operator("bim.change_extrusion_depth", icon="FILE_REFRESH", text="")
            op.depth = cls.props.extrusion_depth

            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="length", text="Length")
            op = row.operator("bim.change_layer_length", icon="FILE_REFRESH", text="")
            op.length = cls.props.length

            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="x_angle", text="X Angle")
            op = row.operator("bim.change_extrusion_x_angle", icon="FILE_REFRESH", text="")
            op.x_angle = cls.props.x_angle

            add_layout_hotkey_operator(cls.layout, "Extend", "S_E", "")
            add_layout_hotkey_operator(cls.layout, "Butt", "S_T", "")
            add_layout_hotkey_operator(cls.layout, "Mitre", "S_Y", "")

            add_layout_hotkey_operator(cls.layout, "Merge", "S_M", bpy.ops.bim.merge_wall.__doc__)
            add_layout_hotkey_operator(cls.layout, "Flip", "S_F", bpy.ops.bim.flip_wall.__doc__)
            add_layout_hotkey_operator(cls.layout, "Split", "S_K", bpy.ops.bim.split_wall.__doc__)
            add_layout_hotkey_operator(cls.layout, "Rotate 90", "S_R", bpy.ops.bim.rotate_90.__doc__)
            add_layout_hotkey_operator(cls.layout, "Regen", "S_G", bpy.ops.bim.recalculate_wall.__doc__)
            row.operator("bim.join_wall", icon="X", text="").join_type = ""

        elif AuthoringData.data["active_material_usage"] == "LAYER3":

            if len(context.selected_objects) == 1:
                add_layout_hotkey_operator(cls.layout, "Edit Profile", "S_E", "")
            elif "LAYER2" in AuthoringData.data["selected_material_usages"]:
                add_layout_hotkey_operator(cls.layout, "Extend Wall To Slab", "S_E", "")

            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="x_angle", text="X Angle")
            op = row.operator("bim.change_extrusion_x_angle", icon="FILE_REFRESH", text="")
            op.x_angle = cls.props.x_angle

        elif AuthoringData.data["active_material_usage"] == "PROFILE":
            row = cls.layout.row(align=True)
            row.prop(data=cls.props, property="cardinal_point", text="Axis")
            op = row.operator("bim.change_cardinal_point", icon="FILE_REFRESH", text="")
            op.cardinal_point = int(cls.props.cardinal_point)

            row = cls.layout.row(align=True)
            label = (
                "Height" if AuthoringData.data["active_class"] in ("IfcColumn", "IfcColumnStandardCase") else "Length"
            )
            row.prop(data=cls.props, property="extrusion_depth", text=label)
            op = row.operator("bim.change_profile_depth", icon="FILE_REFRESH", text="")
            op.depth = cls.props.extrusion_depth

            add_layout_hotkey_operator(cls.layout, "Extend", "S_E", "")
            add_layout_hotkey_operator(cls.layout, "Edit Axis", "A_E", "")
            add_layout_hotkey_operator(cls.layout, "Butt", "S_T", "")
            add_layout_hotkey_operator(cls.layout, "Mitre", "S_Y", "")
            add_layout_hotkey_operator(cls.layout, "Rotate 90", "S_R", bpy.ops.bim.rotate_90.__doc__)
            add_layout_hotkey_operator(cls.layout, "Regen", "S_G", bpy.ops.bim.recalculate_profile.__doc__)
            row.operator("bim.extend_profile", icon="X", text="").join_type = ""

        elif (
            (RailingData.is_loaded or not RailingData.load())
            and RailingData.data["pset_data"]
            and not context.active_object.BIMRailingProperties.is_editing_path
        ):
            # NOTE: should be above "active_representation_type" = "SweptSolid" check
            # because it could be a SweptSolid too
            row = cls.layout.row(align=True)
            row.label(text="", icon=f"EVENT_TAB")
            row.operator("bim.enable_editing_railing_path", text="Edit Railing Path")

        elif AuthoringData.data["active_representation_type"] == "SweptSolid":
            add_layout_hotkey_operator(cls.layout, "Edit Profile", "S_E", "")

        elif AuthoringData.data["active_class"] in (
            "IfcWindow",
            "IfcWindowStandardCase",
            "IfcDoor",
            "IfcDoorStandardCase",
        ):
            if AuthoringData.data["active_class"] in ("IfcWindow", "IfcWindowStandardCase"):
                row = cls.layout.row(align=True)
                row.prop(data=cls.props, property="rl2", text="RL")
            elif AuthoringData.data["active_class"] in ("IfcDoor", "IfcDoorStandardCase"):
                row = cls.layout.row(align=True)
                row.prop(data=cls.props, property="rl1", text="RL")

            add_layout_hotkey_operator(cls.layout, "Regen", "S_G", bpy.ops.bim.recalculate_fill.__doc__)
            add_layout_hotkey_operator(cls.layout, "Flip", "S_F", "")

        elif AuthoringData.data["active_class"] in ("IfcSpace",):
            add_layout_hotkey_operator(cls.layout, "Regen", "S_G", bpy.ops.bim.generate_space.__doc__)

        elif AuthoringData.data["active_class"] in (
            "IfcCableCarrierSegmentType",
            "IfcCableSegmentType",
            "IfcDuctSegmentType",
            "IfcPipeSegmentType",
        ):
            add_layout_hotkey_operator(cls.layout, "Extend", "S_E", "")

        elif (
            (RoofData.is_loaded or not RoofData.load())
            and RoofData.data["pset_data"]
            and not context.active_object.BIMRoofProperties.is_editing_path
        ):
            row = cls.layout.row(align=True)
            row.label(text="", icon=f"EVENT_TAB")
            row.operator("bim.enable_editing_roof_path", text="Edit Roof Path")

        row = cls.layout.row(align=True)
        row.label(text="", icon="EVENT_SHIFT")
        row.label(text="", icon="EVENT_O")

        if len(context.selected_objects) == 2:
            row.operator("bim.add_opening", text="Apply Void")
        else:
            row.operator("bim.add_potential_opening", text="Add Void")

        if AuthoringData.data["is_voidable_element"]:
            if AuthoringData.data["has_visible_openings"]:
                row.operator("bim.edit_openings", icon="CHECKMARK", text="")
                row.operator("bim.hide_openings", icon="CANCEL", text="")
            else:
                row.operator("bim.show_openings", icon="HIDE_OFF", text="")

        cls.layout.row(align=True).label(text="Align")
        add_layout_hotkey_operator(cls.layout, "Align Exterior", "S_X", "")
        add_layout_hotkey_operator(cls.layout, "Align Centerline", "S_C", "")
        add_layout_hotkey_operator(cls.layout, "Align Interior", "S_V", "")
        add_layout_hotkey_operator(cls.layout, "Mirror", "S_M", bpy.ops.bim.mirror_elements.__doc__)

        cls.layout.row(align=True).label(text="Mode")
        add_layout_hotkey_operator(cls.layout, "Void", "A_O", "Toggle openings")
        add_layout_hotkey_operator(cls.layout, "Decomposition", "A_D", "Select decomposition")

    @classmethod
    def draw_header_interface(cls):
        cls.draw_type_selection_interface()

        if AuthoringData.data["ifc_classes"]:
            row = cls.layout.row(align=True)
            row.label(text="", icon="EVENT_SHIFT")
            row.label(text="", icon="EVENT_A")
            op = row.operator("bim.add_constr_type_instance", text="Add")
            op.from_invoke = True
            op.ifc_class = cls.props.ifc_class
            if cls.props.relating_type_id.isnumeric():
                op.relating_type_id = int(cls.props.relating_type_id)

    @classmethod
    def draw_type_selection_interface(cls):
        # shared by both sidebar and header
        row = cls.layout.row(align=True)
        if AuthoringData.data["ifc_classes"]:
            row.label(text="", icon="FILE_VOLUME")
            prop_with_search(row, cls.props, "ifc_class", text="")

            row = cls.layout.row(align=True)
            if AuthoringData.data["relating_type_id"]:
                row.label(text="", icon="FILE_3D")
                prop_with_search(row, cls.props, "relating_type_id", text="")
            else:
                row.label(text="No Construction Type", icon="FILE_3D")
        else:
            row.label(text="No Construction Class", icon="FILE_VOLUME")
        row.operator("bim.launch_type_manager", icon="LIGHTPROBE_GRID", text="")

    @classmethod
    def draw_basic_bim_tool_interface(cls):
        cls.draw_type_selection_interface()

        if AuthoringData.data["ifc_classes"]:
            if cls.props.ifc_class:
                box = cls.layout.box()
                if AuthoringData.data["type_thumbnail"]:
                    box.template_icon(icon_value=AuthoringData.data["type_thumbnail"], scale=5)
                else:
                    op = box.operator("bim.load_type_thumbnails", text="Load Thumbnails", icon="FILE_REFRESH")
                    op.ifc_class = cls.props.ifc_class

            row = cls.layout.row(align=True)
            row.label(text="", icon="EVENT_SHIFT")
            row.label(text="", icon="EVENT_A")
            op = row.operator("bim.add_constr_type_instance", text="Add")
            op.from_invoke = True
            op.ifc_class = cls.props.ifc_class
            if cls.props.relating_type_id.isnumeric():
                op.relating_type_id = int(cls.props.relating_type_id)


class Hotkey(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bim.hotkey"
    bl_label = "Hotkey"
    bl_options = {"REGISTER", "UNDO"}
    hotkey: bpy.props.StringProperty()
    description: bpy.props.StringProperty()
    x: bpy.props.FloatProperty(name="X", default=0.5)
    y: bpy.props.FloatProperty(name="Y", default=0.5)
    z: bpy.props.FloatProperty(name="Z", default=0.5)

    @classmethod
    def poll(cls, context):
        return tool.Ifc.get()

    @classmethod
    def description(cls, context, operator):
        return operator.description or ""

    def _execute(self, context):
        self.props = context.scene.BIMModelProperties
        self.has_ifc_class = True

        self.active_class = None
        self.active_material_usage = None
        element = tool.Ifc.get_entity(context.active_object)
        if element:
            self.active_class = element.is_a()
            self.active_material_usage = tool.Model.get_usage_type(element)

        if get_ifc_class(None, None):
            try:
                self.has_ifc_class = bool(self.props.ifc_class)
            except:
                pass
        getattr(self, f"hotkey_{self.hotkey}")()

    def invoke(self, context, event):
        # https://blender.stackexchange.com/questions/276035/how-do-i-make-operators-remember-their-property-values-when-called-from-a-hotkey
        self.props = context.scene.BIMModelProperties
        self.x = self.props.x
        self.y = self.props.y
        self.z = self.props.z
        return self.execute(context)

    def draw(self, context):
        if self.hotkey == "S_O":
            row = self.layout.row()
            row.prop(self, "x")
            row = self.layout.row()
            row.prop(self, "y")
            row = self.layout.row()
            row.prop(self, "z")

    def hotkey_S_A(self):
        bpy.ops.bim.add_constr_type_instance()

    def hotkey_S_Q(self):
        if not bpy.context.selected_objects:
            return

        bpy.ops.bim.calculate_all_quantities()

    def hotkey_C_P(self):
        if not bpy.context.selected_objects:
            return
        bpy.ops.bim.assign_object()

    def hotkey_A_P(self):
        if not bpy.context.selected_objects:
            return
        bpy.ops.bim.unassign_object()

    def hotkey_S_C(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.align_wall(align_type="CENTERLINE")
        else:
            bpy.ops.bim.align_product(align_type="CENTERLINE")

    def hotkey_S_E(self):
        if not bpy.context.selected_objects:
            return

        # NOTE: placing it before the other operations because railing can also be SweptSolid
        # and it might conflict with one of the conditions below
        if (
            (RailingData.is_loaded or not RailingData.load())
            and RailingData.data["pset_data"]
            and not bpy.context.active_object.BIMRailingProperties.is_editing_path
        ):
            bpy.ops.bim.enable_editing_railing_path()
            return

        elif (
            (RoofData.is_loaded or not RoofData.load())
            and RoofData.data["pset_data"]
            and not bpy.context.active_object.BIMRoofProperties.is_editing_path
        ):
            # undo the unselection done above because roof has no usage type
            bpy.ops.bim.enable_editing_roof_path()
            return

        selected_usages = {}
        for obj in bpy.context.selected_objects:
            element = tool.Ifc.get_entity(obj)
            if not element:
                obj.select_set(False)
                continue
            usage = tool.Model.get_usage_type(element)
            if not usage:
                representation = tool.Geometry.get_active_representation(obj)
                if representation and representation.RepresentationType == "SweptSolid":
                    usage = "SWEPTSOLID"
                else:
                    obj.select_set(False)
                    continue
            selected_usages.setdefault(usage, []).append(obj)

        if len(bpy.context.selected_objects) == 1:
            if self.active_material_usage == "LAYER3":
                # Edit LAYER3 profile
                if bpy.context.active_object and bpy.context.active_object.mode == "OBJECT":
                    bpy.ops.bim.enable_editing_extrusion_profile()
            elif self.active_material_usage == "LAYER2":
                # Extend LAYER2 to cursor
                bpy.ops.bim.join_wall(join_type="T")
            elif self.active_material_usage == "PROFILE":
                # Extend PROFILE to cursor
                bpy.ops.bim.extend_profile(join_type="T")
            else:
                # Edit SWEPTSOLID profile (assuming single profile for now)
                bpy.ops.bim.enable_editing_extrusion_profile()

        elif self.active_material_usage == "LAYER2" and selected_usages.get("PROFILE", []):
            # Extend PROFILEs to LAYER2
            [o.select_set(False) for o in selected_usages.get("LAYER3", [])]
            [o.select_set(False) for o in selected_usages.get("LAYER2", []) if o != bpy.context.active_object]
            bpy.ops.bim.extend_profile(join_type="T")

        elif self.active_material_usage == "LAYER3" and selected_usages.get("LAYER2", []):
            # Extend LAYER2s to LAYER3
            [o.select_set(False) for o in selected_usages.get("PROFILE", [])]
            [o.select_set(False) for o in selected_usages.get("LAYER3", []) if o != bpy.context.active_object]
            bpy.ops.bim.join_wall(join_type="T")

        elif self.active_material_usage == "LAYER2":
            # Extend LAYER2s to LAYER2
            [o.select_set(False) for o in selected_usages.get("LAYER3", [])]
            [o.select_set(False) for o in selected_usages.get("PROFILE", [])]
            bpy.ops.bim.join_wall(join_type="T")

        elif self.active_material_usage == "PROFILE":
            # Extend PROFILEs to PROFILE
            [o.select_set(False) for o in selected_usages.get("LAYER3", [])]
            [o.select_set(False) for o in selected_usages.get("LAYER2", [])]
            bpy.ops.bim.extend_profile(join_type="T")

    def hotkey_S_F(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.flip_wall()
        elif self.active_class in ("IfcWindow", "IfcWindowStandardCase", "IfcDoor", "IfcDoorStandardCase"):
            bpy.ops.bim.flip_fill()

    def hotkey_S_G(self):
        if not bpy.context.selected_objects:
            if self.props.ifc_class == "IfcSpaceType":
                bpy.ops.bim.generate_space()
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.recalculate_wall()
        elif self.active_material_usage == "PROFILE":
            bpy.ops.bim.recalculate_profile()
        elif self.active_class in ("IfcWindow", "IfcWindowStandardCase", "IfcDoor", "IfcDoorStandardCase"):
            bpy.ops.bim.recalculate_fill()
        elif self.active_class in ("IfcSpace"):
            bpy.ops.bim.generate_space()

    def hotkey_S_M(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.merge_wall()
        else:
            if len(bpy.context.selected_objects) == 1:
                self.report(
                    {"INFO"},
                    "At least two objects must be selected: an object to be mirrored, and a mirror axis as the active object.",
                )
            else:
                bpy.ops.bim.mirror_elements()

    def hotkey_S_R(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.rotate_90(axis="Z")
        elif self.active_class in ("IfcColumn", "IfcColumnStandardCase"):
            bpy.ops.bim.rotate_90(axis="Z")
        elif self.active_class in ("IfcBeam", "IfcBeamStandardCase", "IfcMember", "IfcMemberStandardCase"):
            bpy.ops.bim.rotate_90(axis="Y")

    def hotkey_S_K(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.split_wall()

    def hotkey_S_T(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.join_wall(join_type="L")
        elif self.active_material_usage == "PROFILE":
            bpy.ops.bim.extend_profile(join_type="L")

    def hotkey_S_V(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.align_wall(align_type="INTERIOR")
        else:
            bpy.ops.bim.align_product(align_type="POSITIVE")

    def hotkey_S_X(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            if bpy.ops.bim.align_wall.poll():
                bpy.ops.bim.align_wall(align_type="EXTERIOR")
        else:
            bpy.ops.bim.align_product(align_type="NEGATIVE")

    def hotkey_S_Y(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "LAYER2":
            bpy.ops.bim.join_wall(join_type="V")
        elif self.active_material_usage == "PROFILE":
            bpy.ops.bim.extend_profile(join_type="V")

    def hotkey_S_B(self):
        bpy.ops.bim.add_boundary()

    def hotkey_S_O(self):
        if len(bpy.context.selected_objects) == 2:
            bpy.ops.bim.add_opening()
        else:
            unit_scale = ifcopenshell.util.unit.calculate_unit_scale(tool.Ifc.get())
            bpy.ops.bim.add_potential_opening(x=self.x * unit_scale, y=self.y * unit_scale, z=self.z * unit_scale)
            self.props.x = self.x
            self.props.y = self.y
            self.props.z = self.z

    def hotkey_A_D(self):
        if not bpy.context.selected_objects:
            return
        bpy.ops.bim.select_decomposition()

    def hotkey_A_E(self):
        if not bpy.context.selected_objects:
            return
        if self.active_material_usage == "PROFILE":
            bpy.ops.bim.enable_editing_extrusion_axis()

    def hotkey_A_O(self):
        if not bpy.context.selected_objects:
            return
        if AuthoringData.data["has_visible_openings"]:
            bpy.ops.bim.edit_openings()
        else:
            bpy.ops.bim.show_openings()

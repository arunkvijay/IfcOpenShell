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
import addon_utils
import ifcopenshell.api.owner.settings
import blenderbim.tool as tool
import blenderbim.core.owner as core_owner
from bpy.app.handlers import persistent
from blenderbim.bim.ifc import IfcStore
from blenderbim.bim.module.owner.prop import get_user_person, get_user_organisation
from blenderbim.bim.module.model.data import AuthoringData
from mathutils import Vector
from math import cos, degrees


cwd = os.path.dirname(os.path.realpath(__file__))
global_subscription_owner = object()


def mode_callback(obj, data):
    objects = bpy.context.selected_objects
    if bpy.context.active_object:
        objects += [bpy.context.active_object]
    for obj in objects:
        if (
            obj.mode != "EDIT"
            or not obj.data
            or not isinstance(obj.data, (bpy.types.Mesh, bpy.types.Curve, bpy.types.TextCurve))
            or not obj.BIMObjectProperties.ifc_definition_id
        ):
            continue
        if obj.data.BIMMeshProperties.ifc_definition_id:
            tool.Ifc.edit(obj)
        elif IfcStore.get_file().by_id(obj.BIMObjectProperties.ifc_definition_id).is_a("IfcGridAxis"):
            tool.Ifc.edit(obj)


def name_callback(obj, data):
    try:
        obj.name
    except:
        # The object is invalid but somehow still has a callback. Clear all
        # msgbus subscriptions to prevent useless further triggers.
        bpy.msgbus.clear_by_owner(obj)
        return  # In case the object RNA is gone during an undo / redo operation
    # Blender names are up to 63 UTF-8 bytes
    if len(bytes(obj.name, "utf-8")) >= 63:
        return

    if isinstance(obj, bpy.types.Material):
        if obj.BIMObjectProperties.ifc_definition_id:
            IfcStore.get_file().by_id(obj.BIMObjectProperties.ifc_definition_id).Name = obj.name
        if obj.BIMMaterialProperties.ifc_style_id:
            IfcStore.get_file().by_id(obj.BIMMaterialProperties.ifc_style_id).Name = obj.name
        refresh_ui_data()
        return

    if not obj.BIMObjectProperties.ifc_definition_id or "/" not in obj.name:
        return
    element = IfcStore.get_file().by_id(obj.BIMObjectProperties.ifc_definition_id)
    if element.is_a("IfcGridAxis"):
        element.AxisTag = obj.name.split("/")[1]
        refresh_ui_data()
    if not element.is_a("IfcRoot"):
        return
    if obj.BIMObjectProperties.collection:
        obj.BIMObjectProperties.collection.name = obj.name
    element.Name = "/".join(obj.name.split("/")[1:])
    refresh_ui_data()


def color_callback(obj, data):
    if obj.BIMMaterialProperties.ifc_style_id:
        tool.Ifc.edit(obj)


def active_object_callback():
    refresh_ui_data()
    update_bim_tool_props()


def update_bim_tool_props():
    """update BIM Tools props (such as extrusion_depth, length and x_angle) when active object changes"""
    obj = bpy.context.active_object

    # bunch of checks to see if we're in a valid state
    if not obj:
        return
    mode = bpy.context.mode
    current_tool = bpy.context.workspace.tools.from_space_view3d_mode(mode)
    if not current_tool or current_tool.idname != "bim.bim_tool":
        return
    element = tool.Ifc.get_entity(obj)
    if not element:
        return
    representation = ifcopenshell.util.representation.get_representation(element, "Model", "Body", "MODEL_VIEW")
    if not representation:
        return
    extrusion = tool.Model.get_extrusion(representation)
    if not extrusion:
        return

    def get_x_angle(extrusion):
        x, y, z = extrusion.ExtrudedDirection.DirectionRatios
        x_angle = Vector((0, 1)).angle_signed(Vector((y, z)))
        return x_angle

    si_conversion = ifcopenshell.util.unit.calculate_unit_scale(tool.Ifc.get())
    props = bpy.context.scene.BIMModelProperties
    if not AuthoringData.is_loaded:
        AuthoringData.load()

    if AuthoringData.data["active_material_usage"] == "LAYER2":
        x_angle = get_x_angle(extrusion)
        axis = tool.Model.get_wall_axis(obj)["reference"]
        props.extrusion_depth = extrusion.Depth * si_conversion * cos(x_angle)
        props.length = (axis[1] - axis[0]).length
        props.x_angle = x_angle

    elif AuthoringData.data["active_material_usage"] == "LAYER3":
        x_angle = get_x_angle(extrusion)
        props.x_angle = x_angle

    elif AuthoringData.data["active_material_usage"] == "PROFILE":
        props.extrusion_depth = extrusion.Depth * si_conversion


def active_material_index_callback(obj, data):
    refresh_ui_data()


def subscribe_to(obj, data_path, callback):
    try:
        subscribe_to = obj.path_resolve(data_path, False)
    except:
        return
    bpy.msgbus.subscribe_rna(
        key=subscribe_to,
        owner=obj,
        args=(
            obj,
            data_path,
        ),
        notify=callback,
        options={
            "PERSISTENT",
        },
    )


def refresh_ui_data():
    from blenderbim.bim import modules

    for name, value in modules.items():
        try:
            getattr(value, "data").refresh()
        except AttributeError:
            pass

    if isinstance(tool.Ifc.get(), ifcopenshell.sqlite):
        tool.Ifc.get().clear_cache()


def purge_module_data():
    from blenderbim.bim import modules

    refresh_ui_data()
    for name, value in modules.items():
        try:
            getattr(getattr(getattr(ifcopenshell.api, name), "data"), "Data").purge()
        except AttributeError:
            pass

        try:
            getattr(value, "prop").purge()
        except AttributeError:
            pass


@persistent
def loadIfcStore(scene):
    IfcStore.purge()
    purge_module_data()
    if not IfcStore.get_file():
        return
    IfcStore.get_schema()
    IfcStore.relink_all_objects()


@persistent
def undo_post(scene):
    if IfcStore.last_transaction != bpy.context.scene.BIMProperties.last_transaction:
        IfcStore.last_transaction = bpy.context.scene.BIMProperties.last_transaction
        IfcStore.undo()
        purge_module_data()
    tool.Ifc.rebuild_element_maps()


@persistent
def redo_post(scene):
    if IfcStore.last_transaction != bpy.context.scene.BIMProperties.last_transaction:
        IfcStore.last_transaction = bpy.context.scene.BIMProperties.last_transaction
        IfcStore.redo()
        purge_module_data()
    tool.Ifc.rebuild_element_maps()


def get_application(ifc):
    # TODO: cache this for even faster application retrieval. It honestly makes a difference on long scripts.
    version = get_application_version()
    for element in ifc.by_type("IfcApplication"):
        if element.ApplicationIdentifier == "BlenderBIM" and element.Version == version:
            return element
    return ifcopenshell.api.run(
        "owner.add_application",
        ifc,
        version=version,
        application_full_name="BlenderBIM Add-on",
        application_identifier="BlenderBIM",
    )


def get_application_version():
    return ".".join(
        [
            str(x)
            for x in [
                addon.bl_info.get("version", (-1, -1, -1))
                for addon in addon_utils.modules()
                if addon.bl_info["name"] == "BlenderBIM"
            ][0]
        ]
    )


def viewport_shading_changed_callback(area):
    shading = area.spaces.active.shading.type
    if shading == "RENDERED":
        bpy.context.scene.BIMStylesProperties.active_style_type = "External"


if getattr(bpy.types, "SCENE_PT_scene"):

    class Override_SCENE_PT_scene(bpy.types.SCENE_PT_scene):
        bl_idname = "SCENE_PT_scene_override"

        @classmethod
        def poll(cls, context):
            return tool.Blender.is_tab(context, "BLENDER")


if getattr(bpy.types, "SCENE_PT_unit"):

    class Override_SCENE_PT_unit(bpy.types.SCENE_PT_unit):
        bl_idname = "SCENE_PT_unit_override"

        @classmethod
        def poll(cls, context):
            return tool.Blender.is_tab(context, "BLENDER")


if getattr(bpy.types, "SCENE_PT_physics"):

    class Override_SCENE_PT_physics(bpy.types.SCENE_PT_physics):
        bl_idname = "SCENE_PT_physics_override"

        @classmethod
        def poll(cls, context):
            return tool.Blender.is_tab(context, "BLENDER")


if getattr(bpy.types, "SCENE_PT_rigid_body_world"):

    class Override_SCENE_PT_rigid_body_world(bpy.types.SCENE_PT_rigid_body_world):
        bl_idname = "SCENE_PT_rigid_body_world_override"

        @classmethod
        def poll(cls, context):
            return tool.Blender.is_tab(context, "BLENDER")


if getattr(bpy.types, "SCENE_PT_audio"):

    class Override_SCENE_PT_audio(bpy.types.SCENE_PT_audio):
        bl_idname = "SCENE_PT_audio_override"

        @classmethod
        def poll(cls, context):
            return tool.Blender.is_tab(context, "BLENDER")


if getattr(bpy.types, "SCENE_PT_keying_sets"):

    class Override_SCENE_PT_keying_sets(bpy.types.SCENE_PT_keying_sets):
        bl_idname = "SCENE_PT_keying_sets_override"

        @classmethod
        def poll(cls, context):
            return tool.Blender.is_tab(context, "BLENDER")


if getattr(bpy.types, "SCENE_PT_custom_props"):

    class Override_SCENE_PT_custom_props(bpy.types.SCENE_PT_custom_props):
        bl_idname = "SCENE_PT_custom_props_override"

        @classmethod
        def poll(cls, context):
            return tool.Blender.is_tab(context, "BLENDER")


@persistent
def load_post(scene):
    global global_subscription_owner
    active_object_key = bpy.types.LayerObjects, "active"
    bpy.msgbus.subscribe_rna(
        key=active_object_key, owner=global_subscription_owner, args=(), notify=active_object_callback
    )

    # subscribe to changes in viewport shading mode
    # NOTE: couldn't find a way to make it work for new areas too
    # it starts working for them after blender restart though
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            shading = area.spaces.active.shading
            key = shading.path_resolve("type", False)

            bpy.msgbus.subscribe_rna(
                key=key, owner=global_subscription_owner, args=(area,), notify=viewport_shading_changed_callback
            )

    ifcopenshell.api.owner.settings.get_user = lambda ifc: core_owner.get_user(tool.Owner)
    ifcopenshell.api.owner.settings.get_application = get_application
    AuthoringData.type_thumbnails = {}

    if bpy.context.preferences.addons["blenderbim"].preferences.should_setup_workspace:
        if "BIM" in bpy.data.workspaces:
            bpy.context.window.workspace = bpy.data.workspaces["BIM"]
        else:
            bpy.ops.workspace.append_activate(idname="BIM", filepath=os.path.join(cwd, "data", "workspace.blend"))

        # To improve usability for new users, we hijack the scene properties
        # tab. We override default scene properties panels with our own poll
        # to hide them unless the user has chosen to view Blender properties.
        for panel in [
            "SCENE_PT_scene",
            "SCENE_PT_unit",
            "SCENE_PT_physics",
            "SCENE_PT_rigid_body_world",
            "SCENE_PT_audio",
            "SCENE_PT_keying_sets",
            "SCENE_PT_custom_props",
        ]:
            if getattr(bpy.types, panel, None):
                try:
                    bpy.utils.register_class(globals()[f"Override_{panel}"])
                    bpy.utils.unregister_class(getattr(bpy.types, panel))
                except:
                    pass

    # https://blender.stackexchange.com/questions/140644/how-can-make-the-state-of-a-boolean-property-relative-to-the-3d-view-area
    for screen in bpy.data.screens:
        if len(screen.BIMAreaProperties) == 20:
            continue
        screen.BIMAreaProperties.clear()
        for i in range(20):  # 20 is an arbitrary value of split areas
            screen.BIMAreaProperties.add()

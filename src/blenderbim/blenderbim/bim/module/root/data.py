# BlenderBIM Add-on - OpenBIM Blender Add-on
# Copyright (C) 2021 Dion Moult <dion@thinkmoult.com>
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

from collections import defaultdict
import bpy
import ifcopenshell.util.element
from ifcopenshell.util.doc import get_entity_doc, get_predefined_type_doc
import blenderbim.tool as tool
from blenderbim.bim.ifc import IfcStore


def refresh():
    IfcClassData.is_loaded = False


class IfcClassData:
    data = {}
    is_loaded = False

    @classmethod
    def load(cls):
        cls.is_loaded = True
        cls.data = {}
        cls.data["ifc_products"] = cls.ifc_products()
        cls.data["ifc_classes"] = cls.ifc_classes()
        cls.data["ifc_classes_suggestions"] = cls.ifc_classes_suggestions()  # Call AFTER cls.ifc_classes()
        cls.data["contexts"] = cls.contexts()
        cls.data["has_entity"] = cls.has_entity()
        cls.data["name"] = cls.name()
        cls.data["ifc_class"] = cls.ifc_class()
        cls.data["ifc_predefined_types"] = cls.ifc_predefined_types()
        cls.data["can_reassign_class"] = cls.can_reassign_class()

    @classmethod
    def ifc_products(cls):
        products = [
            "IfcElement",
            "IfcElementType",
            "IfcSpatialElement",
            "IfcSpatialElementType",
            "IfcGroup",
            "IfcStructuralItem",
            "IfcContext",
            "IfcAnnotation",
            "IfcRelSpaceBoundary",
        ]
        version = tool.Ifc.get_schema()
        if version == "IFC2X3":
            products = [
                "IfcElement",
                "IfcElementType",
                "IfcSpatialStructureElement",
                "IfcGroup",
                "IfcStructuralItem",
                "IfcAnnotation",
                "IfcRelSpaceBoundary",
            ]
        return [(e, e, (get_entity_doc(version, e) or {}).get("description", "")) for e in products]

    @classmethod
    def ifc_classes(cls):
        ifc_product = bpy.context.scene.BIMRootProperties.ifc_product
        declaration = tool.Ifc.schema().declaration_by_name(ifc_product)
        declarations = ifcopenshell.util.schema.get_subtypes(declaration)
        names = [d.name() for d in declarations]
        if ifc_product == "IfcElementType" and tool.Ifc.get_schema() in ("IFC2X3", "IFC4"):
            names.extend(("IfcDoorStyle", "IfcWindowStyle"))
        if ifc_product == "IfcElement":
            names.remove("IfcOpeningElement")
            if tool.Ifc.get_schema() == "IFC4":
                # Yeah, weird isn't it.
                names.remove("IfcOpeningStandardCase")
        version = tool.Ifc.get_schema()
        return [(c, c, (get_entity_doc(version, c) or {}).get("description", "")) for c in sorted(names)]

    @classmethod
    def ifc_predefined_types(cls):
        types_enum = []
        ifc_class = bpy.context.scene.BIMRootProperties.ifc_class
        declaration = tool.Ifc.schema().declaration_by_name(ifc_class)
        version = tool.Ifc.get_schema()
        for attribute in declaration.attributes():
            if attribute.name() == "PredefinedType":
                types_enum.extend(
                    [
                        (e, e, get_predefined_type_doc(version, ifc_class, e) or "")
                        for e in attribute.type_of_attribute().declared_type().enumeration_items()
                    ]
                )
                break
        return types_enum

    @classmethod
    def ifc_classes_suggestions(cls):
        suggestions = defaultdict(list)
        suggestions.update(
            {
                "IfcWall": ["Glazing", "Glass", "Pane"],
                "IfcWindow": ["Glazing", "Glass", "Pane"],
                "IfcPlate": ["Glazing", "Glass", "Pane"],
                "IfcFurniture": ["Signage"],
                "IfcSlab": ["Hob"],
                "IfcCovering": ["Flashing", "Capping"],
                "IfcCableSegment": ["Lighting Rod"],
                "IfcSensor": ["Card Reader", "Fob Reader"],
                "IfcSwitchingDevice": ["Reed Switch", "Electric Isolating Switch"],
                "IfcActuator": ["Electric Strike"],
                "IfcAirTerminalBox": ["VAV Box"],
                "IfcUnitaryEquipment": ["Fan Coil Unit"],
            }
        )
        version = tool.Ifc.get_schema()
        for ifc_class, _, _ in cls.data["ifc_classes"]:
            class_doc = get_entity_doc(version, ifc_class) or {}
            predefined_types = class_doc.get("predefined_types", {})
            suggestions[ifc_class].extend(predefined_types.keys())
        return suggestions

    @classmethod
    def contexts(cls):
        results = []
        for element in tool.Ifc.get().by_type("IfcGeometricRepresentationContext", include_subtypes=False):
            results.append((str(element.id()), element.ContextType or "Unnamed", ""))
        for element in tool.Ifc.get().by_type("IfcGeometricRepresentationSubContext", include_subtypes=False):
            results.append(
                (
                    str(element.id()),
                    "{}/{}/{}".format(
                        element.ContextType or "Unnamed",
                        element.ContextIdentifier or "Unnamed",
                        element.TargetView or "Unnamed",
                    ),
                    "",
                )
            )
        return results

    @classmethod
    def has_entity(cls):
        try:
            return tool.Ifc.get_entity(bpy.context.active_object)
        except:
            pass

    @classmethod
    def name(cls):
        element = tool.Ifc.get_entity(bpy.context.view_layer.objects.active)
        if not element:
            return
        name = element.is_a()
        predefined_type = ifcopenshell.util.element.get_predefined_type(element)
        if predefined_type:
            name += f"[{predefined_type}]"
        return name

    @classmethod
    def ifc_class(cls):
        element = tool.Ifc.get_entity(bpy.context.view_layer.objects.active)
        if element:
            return element.is_a()

    @classmethod
    def can_reassign_class(cls):
        element = tool.Ifc.get_entity(bpy.context.view_layer.objects.active)
        if element:
            if element.is_a("IfcOpeningElement") or element.is_a("IfcOpeningStandardCase"):
                return False
            for product in cls.ifc_products():
                if element.is_a(product[0]):
                    return True

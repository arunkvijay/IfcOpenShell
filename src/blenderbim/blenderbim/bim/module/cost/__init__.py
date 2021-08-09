import bpy
from . import ui, prop, operator

classes = (
    operator.AddCostSchedule,
    operator.RemoveCostSchedule,
    operator.EditCostSchedule,
    operator.EditCostItem,
    operator.EditCostItemQuantity,
    operator.EditCostValue,
    operator.EnableEditingCostSchedule,
    operator.EnableEditingCostItems,
    operator.EnableEditingCostItem,
    operator.EnableEditingCostItemQuantities,
    operator.EnableEditingCostItemQuantity,
    operator.EnableEditingCostItemValues,
    operator.EnableEditingCostItemValue,
    operator.DisableEditingCostItem,
    operator.DisableEditingCostSchedule,
    operator.DisableEditingCostItemQuantity,
    operator.DisableEditingCostItemValue,
    operator.AddCostItem,
    operator.AddSummaryCostItem,
    operator.ExpandCostItem,
    operator.ContractCostItem,
    operator.RemoveCostItem,
    operator.AssignCostItemProduct,
    operator.UnassignCostItemProduct,
    operator.AddCostItemQuantity,
    operator.RemoveCostItemQuantity,
    operator.AddCostValue,
    operator.RemoveCostItemValue,
    operator.CopyCostItemValues,
    operator.SelectCostItemProducts,
    operator.SelectCostScheduleProducts,
    operator.ImportCostScheduleCsv,
    prop.CostItem,
    prop.BIMCostProperties,
    ui.BIM_PT_cost_schedules,
    ui.BIM_UL_cost_items,
)


def menu_func_import(self, context):
    self.layout.operator(operator.ImportCostScheduleCsv.bl_idname, text="Cost Schedule (.csv)")


def register():
    bpy.types.Scene.BIMCostProperties = bpy.props.PointerProperty(type=prop.BIMCostProperties)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    del bpy.types.Scene.BIMCostProperties
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

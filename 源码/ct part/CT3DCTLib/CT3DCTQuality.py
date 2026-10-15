"""CT-only DICOM value-unit qualification helpers for CT3D.

This module intentionally lives under ``ct part`` so CT rules remain separate
from the shared CT/MR viewing workflow.
"""


def qualifies_hounsfield_units(image_types, multi_energy_values, rescale_types,
                               slopes, intercepts, transform_tags_complete):
    """Return (eligible, reason) using DICOM CT pixel-value rules.

    Explicit HU is accepted. If Rescale Type is absent, implicit HU is allowed
    only for ORIGINAL, non-LOCALIZER, non-multi-energy CT. Slope/intercept must
    be present, finite, non-zero (slope), and uniform for the series.
    """
    image_types = {str(value).upper() for value in image_types}
    multi_energy_values = {str(value).upper() for value in multi_energy_values}
    rescale_types = {str(value).strip().upper() for value in rescale_types}
    rescale_types.discard("")

    if not transform_tags_complete or not slopes or not intercepts:
        return False, "缺少完整的 CT Rescale Slope/Intercept，不能确认 HU"
    if len(set(slopes)) != 1 or len(set(intercepts)) != 1:
        return False, "同一序列的 CT 强度变换参数不一致"
    if len(rescale_types) > 1:
        return False, "序列内 Rescale Type 不一致"
    if rescale_types == {"HU"}:
        return True, "DICOM 明确声明输出单位为 HU"
    if rescale_types:
        return False, "DICOM 输出单位不是 HU"
    if "ORIGINAL" not in image_types:
        return False, "Rescale Type 缺省且图像未标记为 ORIGINAL；不能推定 HU"
    if "LOCALIZER" in image_types:
        return False, "定位像缺省 Rescale Type；不能推定 HU"
    if "YES" in multi_energy_values:
        return False, "多能量 CT 缺省 Rescale Type；不能推定 HU"
    if len(multi_energy_values - {""}) > 1:
        return False, "多能量 CT 标记不一致；不能推定 HU"
    return True, "符合 DICOM 单能量 ORIGINAL CT 缺省 HU 单位规则"

"""Explicit OTGraphicModel.loc.align contract for newly generated objects.

Saved integer groups 4/5 are alignment codes, never label or icon dimensions.
The generation domain below is a reviewed native subset, not an exhaustive enum:
OTStationModel.mouseDownAt::: initializes (0,0); OTGraphicModel.isHorizontalLoc
recognizes x=1/2 and isVerticalLoc recognizes y=3/4. Existing topology creation
uses those horizontal/vertical pairs. No mixed nonzero pair is established.
Reading archives does not apply this new-object contract. Native clones preserve
their exact saved codes separately; source values are not normalized.
"""
import copy
import math
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, StrictFloat, StrictInt, model_validator
from .tools import Input

GENERATION_ALIGNMENT_PAIRS = frozenset({(0, 0), (1, 0), (2, 0), (0, 3), (0, 4)})
SIGNAL_ALIGNMENT_PAIRS = GENERATION_ALIGNMENT_PAIRS - {(0, 0)}
PLACEMENT_KEYS = frozenset({'x', 'y', 'angle', 'alignment_x', 'alignment_y'})
LEGACY_ALIGNMENT_MESSAGE = (
    'width/height are obsolete placement fields: saved groups 4/5 are native '
    'alignment_x/alignment_y, not pixel dimensions. Explicitly select a reviewed '
    'alignment pair; Station may use 0/0, while Signal must match its actual End. '
    'Do not rename legacy pixel sizes into alignment codes.'
)


def reject_legacy_alignment(value):
    if isinstance(value, dict) and ('width' in value or 'height' in value):
        raise ValueError(LEGACY_ALIGNMENT_MESSAGE)
    return value


def _strict_x(value):
    if type(value) is not int or value not in (0, 1, 2):
        raise ValueError('alignment_x must be an exact integer in reviewed native subset {0,1,2}')
    return value


def _strict_y(value):
    if type(value) is not int or value not in (0, 3, 4):
        raise ValueError('alignment_y must be an exact integer in reviewed native subset {0,3,4}')
    return value


AlignmentX = Annotated[Literal[0, 1, 2], BeforeValidator(_strict_x)]
AlignmentY = Annotated[Literal[0, 3, 4], BeforeValidator(_strict_y)]
Number = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]


def validate_alignment_pair(alignment_x, alignment_y):
    pair = (_strict_x(alignment_x), _strict_y(alignment_y))
    if pair not in GENERATION_ALIGNMENT_PAIRS:
        raise ValueError('New graphics require a reviewed native alignment pair: 0/0, 1/0, 2/0, 0/3 or 0/4; mixed nonzero pairs are unverified')
    return pair


def validate_signal_alignment_pair(alignment_x, alignment_y):
    pair = validate_alignment_pair(alignment_x, alignment_y)
    if pair not in SIGNAL_ALIGNMENT_PAIRS:
        raise ValueError('New Signal requires a directional alignment matching its actual End; 0/0 is not a Signal direction')
    return pair


class AlignedInput(Input):
    alignment_x: AlignmentX
    alignment_y: AlignmentY

    @model_validator(mode='before')
    @classmethod
    def explicit_alignment_fields(cls, value):
        return reject_legacy_alignment(value)

    @model_validator(mode='after')
    def reviewed_alignment_pair(self):
        validate_alignment_pair(self.alignment_x, self.alignment_y)
        return self


class SignalAlignedInput(AlignedInput):
    model_config = {'json_schema_extra': {'oneOf': [
        {'properties': {'alignment_x': {'const': x}, 'alignment_y': {'const': y}}}
        for x, y in sorted(SIGNAL_ALIGNMENT_PAIRS)
    ]}}

    @model_validator(mode='after')
    def directional_signal_alignment(self):
        validate_signal_alignment_pair(self.alignment_x, self.alignment_y)
        return self


class GraphicPlacement(AlignedInput):
    x: Number
    y: Number
    angle: Number


def validate_placement(value):
    """Validate core dictionary ingress without interpreting legacy dimensions."""
    reject_legacy_alignment(value)
    if type(value) is not dict or set(value) != PLACEMENT_KEYS:
        raise ValueError('Explicit placement requires exactly x,y,angle,alignment_x,alignment_y')
    validate_alignment_pair(value['alignment_x'], value['alignment_y'])
    for key in ('x', 'y', 'angle'):
        number = value[key]
        if type(number) not in (int, float) or not math.isfinite(number):
            raise ValueError('Placement coordinates/angle must be finite exact numbers')
    return dict(value)


def make_placement(x, y, *, angle=0, alignment_x=0, alignment_y=0):
    return validate_placement(dict(x=x, y=y, angle=angle,
                                   alignment_x=alignment_x, alignment_y=alignment_y))


def signal_alignment_for_end(end):
    """Reviewed new Signal direction from the actual, validated native owner."""
    from . import writer as w, route_factory as rf
    if w.kind(end) != 'OTEndModel':
        raise ValueError('New Signal direction requires its actual OTEndModel owner')
    rf.layout(end, 'OTEndModel', 7, rf.END, graphic=True)
    return validate_signal_alignment_pair(end.contents[4].value, end.contents[5].value)


def make_signal_placement(end, x, y, *, angle=0):
    """Internal factory helper; generic Station placement keeps its 0/0 default."""
    pair = signal_alignment_for_end(end)
    return make_placement(x, y, angle=angle, alignment_x=pair[0], alignment_y=pair[1])


def validate_signal_placement(value, end):
    placement = validate_placement(value)
    pair = validate_signal_alignment_pair(placement['alignment_x'], placement['alignment_y'])
    if pair != signal_alignment_for_end(end):
        raise ValueError('New Signal alignment must match its actual owner End direction')
    return placement


def validate_generated_signal_alignment(signal):
    """New-generation check only; generic reads/clones preserve source codes."""
    from . import writer as w, route_factory as rf
    if w.kind(signal) != 'OTSignalModel':
        raise ValueError('Generated SignalModel required')
    rf.layout(signal, 'OTSignalModel', 11, rf.SIGNAL, graphic=True)
    owner = signal.contents[7].value
    expected = signal_alignment_for_end(owner)
    pair = validate_signal_alignment_pair(signal.contents[4].value, signal.contents[5].value)
    if pair != expected or owner.contents[11].value is not signal:
        raise ValueError('Generated SignalModel alignment must match its actual owner End direction and reference')
    return pair


def copy_native_alignment(source, target):
    """Preserve source fields in a native clone, without granting new-code support.

    Callers must already validate source identity/layout and source hash. This
    only copies the two native integer groups between the same reviewed model
    class. It cannot be requested by a public placement dictionary.
    """
    from . import writer as w, route_factory as rf
    kind = w.kind(source)
    if kind not in {'OTStationModel', 'OTSignalModel'} or w.kind(target) != kind:
        raise ValueError('Alignment preservation requires matching Station/Signal native models')
    version, encodings = (1, ['i','f','f','f','i','i','@','@','ii','ii']) if kind == 'OTStationModel' else (11, rf.SIGNAL)
    for obj in (source, target):
        rf.layout(obj, kind, version, encodings, graphic=True)
        if len(obj.contents) < 6 or any(obj.contents[i].encodings != [b'i'] or
                len(obj.contents[i].values) != 1 or type(obj.contents[i].value) is not int or
                not -2147483648 <= obj.contents[i].value <= 2147483647 for i in (4, 5)):
            raise ValueError('Native alignment preservation requires exact signed-int32 groups 4/5')
    for index in (4, 5):
        target.contents[index] = copy.deepcopy(source.contents[index])

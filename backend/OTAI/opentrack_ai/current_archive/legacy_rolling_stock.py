"""Normalize the archived stock layouts in the original Demo and Training libraries."""

from . import catalogs, course_factories, writer
from .formation_operations import trailer
from .operating_plan_edit import need
from .stock_operations import CATEGORY_LAYOUT
from .train_factory import validate_template


def append_fields(record, fields, values):
    record.contents.extend(writer.TypedGroup([bytes([code]) for code in field.encode('ascii')], slots)
                           for field, slots in zip(fields, values, strict=True))


def clone_class(record, version):
    copy = course_factories.clone(record)
    copy.clazz = writer.Class(copy.clazz.name, version, copy.clazz.superclass)
    return copy


def copy_wire_record(record):
    return writer.GenericArchivedObject(record.clazz, None, [
        writer.TypedGroup(group.encodings, group.values, group._token) for group in record.contents
    ])


def copy_vehicle_array(array):
    result = copy_wire_record(array)
    for entry in result.contents[1:]:
        entry.value = copy_wire_record(entry.value)
    return result


def upgrade_category(record):
    catalogs.shape(record, 'OTTrainCategory', 11, CATEGORY_LAYOUT[:15])
    result = clone_class(record, 19)
    # Stock 0x6c4b44 uses NSColor.lightGrayColor, confirmed in current native catalogs.
    light_gray = writer.GenericArchivedObject(
        writer.Class(b'NSColor', 0, writer.Class(b'NSObject', 0)), None,
        [writer.TypedValue(b'c', 3), writer.TypedGroup([b'f', b'f'], [0.6666666865348816, 1.0])],
    )
    # The encoder 0x6c513c stores the departure-process boolean inverted.
    append_fields(result, CATEGORY_LAYOUT[15:], (
        [0.0], [0], [light_gray], [0.0, 0.0, 0, 0], [0], [420.0], [0.0], [1], [0], [-1.0, 1.0],
    ))
    return result


def upgrade_train(record):
    version, fields = catalogs.LAYOUTS['OTTrain']
    catalogs.shape(record, 'OTTrain', 12, fields[:19])
    result = clone_class(record, version)
    # Absent v13–16 fields receive the exact defaults from OTTrain.initWithCoder: 0x6c28d4.
    append_fields(result, fields[19:], ([100.0], [0.0], [0, 0.0, 0.0], [0.0]))
    source_arrays = record.contents[2].values[1:]
    engines, trailers = map(catalogs.array, source_arrays)
    vehicles = [*engines, *trailers]
    need(len({id(item) for item in vehicles}) == len(vehicles), 'Legacy formation contains an aliased vehicle record')
    result.contents[2].values[1:] = list(map(copy_vehicle_array, source_arrays))
    engines, trailers = map(catalogs.array, result.contents[2].values[1:])
    # The native v12 decoder calls resetPosInTrain at 0x6bb9b0, numbering engine array then trailer array.
    for position, engine in enumerate(engines, 1):
        catalogs.record(engine, 'OTTrainEngine')
        engine.contents[1].value = position
    for position, car in enumerate(trailers, len(engines) + 1):
        need(writer.kind(car) == 'OTTrailer' and car.clazz.version == 2 and car.contents[0].value in (0, 1),
             'Expected the observed legacy Trailer2 layouts in a Train12 formation')
        car.clazz = writer.Class(car.clazz.name, 3, car.clazz.superclass)
        # Trailer3 adds delta-load auxiliary power, defaulting to zero in 0x6ba364.
        car.contents.append(writer.TypedValue(b'f', 0.0))
        trailer(car)
        car.contents[3].values[1] = position
    validate_template(result)
    return result

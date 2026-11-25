"""Recover current native Course and Timetable shapes without donor service data."""

from . import catalogs, course_factories as factory, writer
from .operating_plan_edit import need


def _shape_only(template, fields):
    # Build every saved group from defaults. Only the native class and nested
    # NSString/array shapes come from the selected seed row.
    shape = factory.clone(template)
    for index, value in enumerate(fields):
        if isinstance(value, str):
            factory.settext(shape, index, value)
        elif isinstance(value, tuple):
            shape.contents[index].values[:] = value
        elif isinstance(value, list):
            array = factory.clone(template.contents[index].value)
            catalogs.array(array)
            writer.set_elements(array, value)
            factory.put(shape, index, array)
        else:
            factory.put(shape, index, value)
    return shape


def service_prototypes(course_archive, timetable_archive, course_id, timetable_key):
    course_root = writer.load_next_compatible(course_archive)[0]
    courses = {catalogs.text(row.contents[0].value): row for row in catalogs.course_items(course_root)}
    table_root = writer.load_next_compatible(timetable_archive)[0]
    timetable = factory.timetable(table_root)
    need(course_root.contents[0].value == 17, 'First-service Course shapes require a current native CourseList marker 17')
    need(course_id in courses, 'First-service donor has no exact selected Course template')
    need(timetable_key in timetable, 'First-service donor has no exact selected Timetable row template')

    # OTCourse.init (00455004), current archive slots (00456b6c).
    course = _shape_only(courses[course_id], ('0', 0.0, [], '', '', 1, 100, (0.0, 0.0),
                                            0, 100, '', '', (0.0, 0.0), '', ''))
    # OTTimetable.init (0067889c), current archive slots (0067b390).
    undefined = 'HH:MM:SS'
    row = _shape_only(timetable[timetable_key], (17, '0', None, 0, 0, '', undefined, undefined, '0', [],
                                                2, 0.0, '0', undefined, undefined, (0, 0, 0, 0), '', 0.0, ''))
    return course, row

def wrap_selection(buffer, prefix, suffix=None, placeholder='text'):
    suffix = prefix if suffix is None else suffix
    if buffer.get_has_selection():
        start, end = buffer.get_selection_bounds()
        selected = buffer.get_text(start, end, True)
        buffer.begin_user_action()
        buffer.delete(start, end)
        buffer.insert(start, prefix + selected + suffix)
        buffer.end_user_action()
    else:
        insert_mark = buffer.get_insert()
        cursor = buffer.get_iter_at_mark(insert_mark)
        buffer.begin_user_action()
        buffer.insert(cursor, prefix + placeholder + suffix)
        buffer.end_user_action()


def prefix_current_lines(buffer, prefix):
    if buffer.get_has_selection():
        start, end = buffer.get_selection_bounds()
    else:
        insert_mark = buffer.get_insert()
        start = buffer.get_iter_at_mark(insert_mark)
        end = start.copy()

    start.set_line_offset(0)
    if not end.ends_line():
        end.forward_to_line_end()

    text = buffer.get_text(start, end, True)
    lines = text.split('\n')
    updated = '\n'.join([
        line if line.startswith(prefix) or not line else prefix + line
        for line in lines
    ])
    if not updated:
        updated = prefix

    buffer.begin_user_action()
    buffer.delete(start, end)
    buffer.insert(start, updated)
    buffer.end_user_action()

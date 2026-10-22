"""Render the owned lab block and retire only the selected host's loopback alias."""
LAB_HOSTS = {'node1': '192.168.0.200', 'node2': '192.168.0.201', 'node3': '192.168.0.202'}
BEGIN = '# BEGIN OPENSTACK IAC LAB'
END = '# END OPENSTACK IAC LAB'


def _remove_loopback_alias(line, hostname):
    ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
    body = line[:-len(ending)] if ending else line
    record, separator, comment = body.partition('#')
    fields = record.split()
    if not fields or fields[0] != '127.0.1.1':
        return line
    aliases = fields[1:]
    kept = [alias for alias in aliases if alias.casefold() != hostname.casefold()]
    if len(kept) == len(aliases):
        return line
    if not kept:
        return separator + comment + ending if separator else ''
    return fields[0] + '\t' + ' '.join(kept) + (' #' + comment if separator else '') + ending


def lab_hosts_render(content, hostname):
    if not isinstance(content, str) or hostname not in LAB_HOSTS:
        raise ValueError('Expected hosts-file text and one of node1, node2 or node3.')
    lines = content.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            raise ValueError('Lab hosts markers are incomplete, repeated or reversed; review before writing.')
    newline = '\r\n' if '\r\n' in content else '\n'
    block = newline.join([BEGIN, *(address + ' ' + node for node, address in LAB_HOSTS.items()), END]) + newline
    if starts:
        lines[starts[0]:ends[0] + 1] = block.splitlines(keepends=True)
    result = ''.join(_remove_loopback_alias(line, hostname) for line in lines)
    if not starts:
        if result and not result.endswith(('\n', '\r')):
            result += newline
        result += block
    return result


class FilterModule:
    def filters(self):
        return {'lab_hosts_render': lab_hosts_render}

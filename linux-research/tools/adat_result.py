#!/usr/bin/env python3
"""Conservative acceptance of one optical test, including transport cleanup."""

def passed(profile, analysis, stats, exit_code, pci_same, unbound, module_removed):
    path = profile.get('optical_path')
    if path not in ('enclosure', 'module'):
        return False
    inp, out = profile.get('input_pair'), profile.get('output_pair')
    if type(inp) is not int or type(out) is not int or not 1 <= inp <= 4 or not 1 <= out <= 4:
        return False
    if profile.get('windows_state', False):
        if (path != 'enclosure' or
            profile.get('transport_channels') != [7+2*inp,8+2*inp] or
            profile.get('output_transport_channels') != [7+2*out,8+2*out] or
            profile.get('input_register') != hex(0x44+inp) or profile.get('output_selector') != 4+out or
            profile.get('allow_idle_dma') is not True):
            return False
    base = 24 if path == 'enclosure' else 16
    mode = profile.get('expectation')
    if mode not in ('loopback', 'isolation') or (mode == 'isolation' and inp == out):
        return False
    return (exit_code == 0 and pci_same and unbound and module_removed
            and profile.get('input_selector') == base + inp
            and profile.get('output_register') == hex(0x40 + base + out)
            and analysis.get('expectation_met') is True
            and analysis.get('expectation') == mode
            and analysis.get('optical_path') == path
            and analysis.get('input_pair') == inp
            and (analysis.get('frames'), analysis.get('rate'), analysis.get('format'))
                == (480000, 48000, 'S24_3LE')
            and stats.get('starts') == '1' and stats.get('stops') == '1'
            and all(stats.get(k) == '0' for k in ('xruns', 'last_error'))
            and all(stats.get(k) == 'Y' for k in ('mute_restored', 'route_restored')))

#!/usr/bin/env python3
"""Activate/deactivate the experimental desktop module and its scoped WP rule."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'avid_native_duplex'
BDF = '0000:81:00.0'
PCI = Path('/sys/bus/pci/devices')/BDF
PARAMS = Path('/sys/module')/MODULE/'parameters'
SINK = 'avid_hd_native_duplex_out'
SOURCE = 'avid_hd_native_duplex_in'
RULE_SOURCE = ROOT/'desktop/91-avid-native-duplex.conf'
RULE_TARGET = Path('/etc/wireplumber/wireplumber.conf.d/91-avid-native-duplex.conf')
STATE_DIR = Path('/run/avid-native-duplex')
STATE_FILE = STATE_DIR/'state.json'
MARKER = 'avid-native-duplex-v1'
KEYS = ('bound','starts','stops','xruns','last_error','total_frames','last_frames',
        'ring_wraps','rx_discarded','max_poll_us','mute_restored','route_restored',
        'max_stream_seconds','playback_starts','playback_stops','capture_starts','capture_stops',
        'playback_xruns','capture_xruns','capture_frames')

def run(args, *, check=True, timeout=20):
    p = subprocess.run([str(x) for x in args],text=True,capture_output=True,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f"Falha em {' '.join(str(x) for x in args)}: {(p.stderr or p.stdout).strip()}")
    return p

def user_command(uid,args,**kw):
    account = pwd.getpwuid(uid)
    if os.geteuid()==0:
        argv = ['/usr/sbin/runuser','-u',account.pw_name,'--','env',
                f'XDG_RUNTIME_DIR=/run/user/{uid}',
                f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus',*args]
    else:
        argv = args
    return run(argv,**kw)

def header():
    with (PCI/'config').open('rb') as f:
        data=f.read(64)
    if len(data)!=64:
        raise RuntimeError('Cabeçalho PCI incompleto.')
    return data.hex()

def module_stats():
    return {k:(PARAMS/k).read_text().strip() for k in KEYS if (PARAMS/k).exists()}

def read_state():
    state=json.loads(STATE_FILE.read_text())
    if state.get('owner')!=MARKER:
        raise RuntimeError('Arquivo de estado não pertence a este gerenciador.')
    return state

def save_state(state):
    STATE_DIR.mkdir(mode=0o755,exist_ok=True)
    temp=STATE_DIR/'state.tmp'
    temp.write_text(json.dumps(state,indent=2)+'\n')
    temp.replace(STATE_FILE)

def sinks(uid):
    return json.loads(user_command(uid,['pactl','--format=json','list','sinks']).stdout)

def find_sink(uid):
    return next((s for s in sinks(uid) if s.get('name')==SINK),None)

def sources(uid):
    return json.loads(user_command(uid,['pactl','--format=json','list','sources']).stdout)

def find_source(uid):
    # Exact hardware-source name; never accept the sink monitor as capture.
    return next((s for s in sources(uid) if s.get('name')==SOURCE),None)

def restore_default_source(uid,previous):
    if previous and any(s.get('name')==previous for s in sources(uid)):
        current=user_command(uid,['pactl','get-default-source']).stdout.strip()
        if current!=previous:
            user_command(uid,['pactl','set-default-source',previous])

def restore_default(uid,previous):
    if previous and any(s.get('name')==previous for s in sinks(uid)):
        current=user_command(uid,['pactl','get-default-sink']).stdout.strip()
        if current!=previous:
            user_command(uid,['pactl','set-default-sink',previous])

def diagnostics(state):
    log=Path(state['log_directory'])
    log.mkdir(parents=True,exist_ok=True)
    stats=module_stats()
    if stats:
        (log/'module-stats.json').write_text(json.dumps(stats,indent=2)+'\n')
    dmesg=run(['dmesg','--notime'],check=False)
    lines=[s for s in dmesg.stdout.splitlines() if MODULE in s]
    begin=[i for i,s in enumerate(lines) if ': begin duplex ALSA session' in s]
    if begin: lines=lines[begin[-1]:]
    (log/'module.log').write_text('\n'.join(lines)+'\n')
    for name,args in [('pipewire.json',['pactl','--format=json','list','sinks']),
                      ('pipewire-sources.json',['pactl','--format=json','list','sources']),
                      ('wireplumber.log',['journalctl','--user','-u','wireplumber','--since',state['started_at'],'--no-pager','-n','150'])]:
        result=user_command(state['uid'],args,check=False)
        (log/name).write_text(result.stdout+result.stderr)
    print('Logs: '+str(log))

def cleanup(state):
    """Close user audio handles before rmmod; always bring WP back afterward."""
    uid=state['uid']
    errors=[]
    removed=not PARAMS.exists()
    try:
        diagnostics(state)
    except Exception as error:
        print('Não consegui salvar todos os diagnósticos: '+str(error),file=sys.stderr)
    wp_was_active=user_command(uid,['systemctl','--user','is-active','--quiet','wireplumber'],check=False).returncode==0
    try:
        if wp_was_active:
            user_command(uid,['systemctl','--user','stop','wireplumber'])
        if PARAMS.exists():
            closed_stats=module_stats()
            try:
                (Path(state['log_directory'])/'after-close-stats.json').write_text(
                    json.dumps(closed_stats,indent=2)+'\n')
            except OSError as error:
                print('Não consegui salvar os contadores finais: '+str(error),file=sys.stderr)
            if int(closed_stats.get('starts','0')) and (
                closed_stats.get('mute_restored')!='Y' or
                closed_stats.get('route_restored')!='Y'):
                errors.append('Restauração de mute/rota não confirmada após fechar o áudio; preserve o log.')
            r=run(['/usr/sbin/rmmod',MODULE],check=False)
            removed=r.returncode==0
            if not removed:
                errors.append('Módulo ainda em uso ou retido: '+r.stderr.strip())
        if removed and RULE_TARGET.exists() and state.get('rule_owned'):
            actual=hashlib.sha256(RULE_TARGET.read_bytes()).hexdigest()
            if actual==state['rule_sha256'] and not RULE_TARGET.is_symlink():
                RULE_TARGET.unlink()
            else:
                errors.append('A regra foi modificada externamente; preservada em '+str(RULE_TARGET))
    finally:
        if wp_was_active or state.get('restart_wireplumber',False):
            user_command(uid,['systemctl','--user','start','wireplumber'])
    if removed:
        after=header()
        same=after==state['pci_before']
        unbound=not (PCI/'driver').exists()
        state['pci_after']=after
        state['pci_restored']=same
        state['pci_unbound']=unbound
        print(f"MODULE_REMOVED=yes PCI_HEADER_RESTORED={'yes' if same else 'no'} PCI_UNBOUND={'yes' if unbound else 'no'}")
        if not same or not unbound:
            errors.append('Restauração PCI não confirmada.')
        # Restore the previous default only if our sink was still selected at stop.
        # WP normally falls back itself when our node disappears.
        if state.get('was_default_on_stop'):
            for _ in range(20):
                if any(s.get('name')==state.get('default_before') for s in sinks(uid)):
                    restore_default(uid,state.get('default_before'))
                    break
                time.sleep(.25)
        if state.get('was_default_source_on_stop'):
            for _ in range(20):
                if any(s.get('name')==state.get('source_before') for s in sources(uid)):
                    restore_default_source(uid,state.get('source_before'))
                    break
                time.sleep(.25)
    state['cleanup_errors']=errors
    save_state(state)
    (Path(state['log_directory'])/'session.json').write_text(json.dumps(state,indent=2)+'\n')
    try:
        diagnostics(state)
    except Exception as error:
        print('Não consegui salvar todos os diagnósticos: '+str(error),file=sys.stderr)
    if removed and not errors:
        STATE_FILE.unlink()
        try: STATE_DIR.rmdir()
        except OSError: pass
    if errors:
        raise RuntimeError('; '.join(errors))

def start():
    uid=int(os.environ.get('SUDO_UID','0'))
    if uid<=0:
        raise RuntimeError('Execute com sudo a partir do terminal de Paulo, para identificar a sessão de áudio.')
    if STATE_FILE.exists():
        if PARAMS.exists():
            print('Módulo já ativado; não alterei o volume nem reiniciei o áudio.')
            status(uid)
            return
        raise RuntimeError('Há estado de uma ativação anterior. Execute duplex-driver.sh stop antes de repetir.')
    if PARAMS.exists() or (PCI/'driver').exists():
        raise RuntimeError('A placa ou o módulo já está em uso fora deste gerenciador.')
    for other in ('avid_native_alsa','avid_native_dma_probe','avid_native_capture','avid_native_desktop'):
        if Path('/sys/module',other).exists():
            raise RuntimeError(f'O módulo de teste {other} precisa ser removido antes.')
    ko=ROOT/f'kernel/{MODULE}.ko'
    vermagic=run(['/usr/sbin/modinfo','-F','vermagic',ko]).stdout.split()[0]
    if vermagic!=os.uname().release:
        raise RuntimeError('Recompile o módulo para o kernel atual antes de ativá-lo.')
    build=json.loads((ROOT/'reports/duplex-build.json').read_text())
    for relative,digest in build['load_files_sha256'].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Artefato mudou após o build: '+relative)
    rule=RULE_SOURCE.read_bytes()
    if RULE_TARGET.is_symlink() or (RULE_TARGET.exists() and RULE_TARGET.read_bytes()!=rule):
        raise RuntimeError('Já existe uma configuração diferente: '+str(RULE_TARGET))
    user_command(uid,['systemctl','--user','is-active','--quiet','wireplumber'])
    previous=user_command(uid,['pactl','get-default-sink']).stdout.strip()
    previous_source=user_command(uid,['pactl','get-default-source']).stdout.strip()
    stamp=time.strftime('%Y%m%d-%H%M%S')
    state={'owner':MARKER,'uid':uid,'user':pwd.getpwuid(uid).pw_name,
           'started_at':time.strftime('%Y-%m-%d %H:%M:%S'),
           'log_directory':str(ROOT/'reports'/f'duplex-session-{stamp}'),
           'pci_before':header(),'rule_sha256':hashlib.sha256(rule).hexdigest(),
           'rule_owned':not RULE_TARGET.exists(),'default_before':previous,'source_before':previous_source,
           'restart_wireplumber':True,'module_sha256':hashlib.sha256(ko.read_bytes()).hexdigest()}
    save_state(state)
    try:
        RULE_TARGET.parent.mkdir(parents=True,exist_ok=True)
        if state['rule_owned']:
            # Exclusive create: never replace an unrelated configuration.
            with RULE_TARGET.open('xb') as f: f.write(rule)
            RULE_TARGET.chmod(0o644)
        print('Aplicando regra da HD Native e reiniciando WirePlumber...',flush=True)
        user_command(uid,['systemctl','--user','restart','wireplumber'])
        run(['/usr/sbin/modprobe','snd_pcm'])
        run(['/usr/sbin/insmod',ko,'enable_experimental=1','max_stream_seconds=0',f'bdf={BDF}'])
        run(['udevadm','settle','--timeout=5'])
        deadline=time.monotonic()+20
        found=None
        while time.monotonic()<deadline:
            found=find_sink(uid)
            if found and find_source(uid): break
            time.sleep(.25)
        if not found or not find_source(uid):
            raise RuntimeError('O módulo carregou, mas a saída PipeWire ou a entrada física não apareceu; veja os logs.')
        if int(module_stats().get('last_error','0')):
            raise RuntimeError('O driver informou falha durante a criação da saída; veja os logs.')
        # Low session priority prevents selection during creation. Set initial
        # user-adjustable volume before reporting the node ready.
        user_command(uid,['pactl','set-sink-volume',SINK,'-40dB'])
        user_command(uid,['pactl','set-sink-mute',SINK,'0'])
        user_command(uid,['pactl','set-source-volume',SOURCE,'100%'])
        user_command(uid,['pactl','set-source-mute',SOURCE,'0'])
        restore_default(uid,previous)
        restore_default_source(uid,previous_source)
        state['source_name']=SOURCE
        state['sink_name']=SINK
        state['initial_volume_db']=-40
        state['ready']=True
        save_state(state)
        diagnostics(state)
        print('DUPLEX_READY=yes')
        print('Selecione as saídas e entradas “Avid HD Native — 192 I/O Duplex” nos aplicativos.')
        print('Volume inicial -40 dB; ajuste gradualmente pelo controle de som. Entrada a 0 dB; não há conexão automática de monitoramento. Teste duplex experimental.')
        print('O módulo ficará carregado até stop ou reinicialização. Não há carga automática no boot.')
    except BaseException:
        try: cleanup(state)
        except Exception as error: print('Falha na limpeza: '+str(error),file=sys.stderr)
        raise

def stop():
    if not STATE_FILE.exists():
        if PARAMS.exists():
            raise RuntimeError('Módulo carregado fora deste gerenciador; não há estado para restaurar.')
        print('Módulo já está desativado.')
        return
    state=read_state()
    current=user_command(state['uid'],['pactl','get-default-sink'],check=False).stdout.strip()
    state['was_default_on_stop']=current==SINK
    source=user_command(state['uid'],['pactl','get-default-source'],check=False).stdout.strip()
    state['was_default_source_on_stop']=source==SOURCE
    cleanup(state)

def status(uid=None):
    uid=uid or (int(os.environ.get('SUDO_UID','0')) if os.geteuid()==0 else os.getuid())
    print(json.dumps({'module_loaded':PARAMS.exists(),'parameters':module_stats()},indent=2))
    if uid:
        print(user_command(uid,['wpctl','status'],check=False).stdout)
    if STATE_FILE.exists():
        print('Logs: '+read_state()['log_directory'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('start','stop','status'))
    a=p.parse_args()
    if a.action!='status' and os.geteuid()!=0:
        p.error('Use sudo somente para start/stop; os aplicativos serão executados normalmente.')
    try:
        {'start':start,'stop':stop,'status':status}[a.action]()
    except Exception as error:
        print('ERRO: '+str(error),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())

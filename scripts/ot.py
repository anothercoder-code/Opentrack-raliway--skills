"""Invoke only the paired, version-checked OpenTrack saved-data backend."""
import sys

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8')


if tuple(sys.version_info[:2]) != (3, 13):
    sys.stderr.write('OpenTrack Skill requires Python 3.13.x. Please run with Python 3.13.\n')
    raise SystemExit(2)

import ast
import json
import importlib.metadata
import shlex
import os
from pathlib import Path
import subprocess

EXPECTED_VERSION = '0.33.1-zeroaccept1'
REQUIRED_TOOLS = {'opentrack_inspect_current_archive', 'opentrack_preview_initialize_project', 'opentrack_initialize_project', 'opentrack_initialize_station_documents_project', 'opentrack_inspect_multi_document_project', 'opentrack_inspect_signal_saved_parameters', 'opentrack_preview_signal_saved_parameters'}
CONFIG_HELP = ('请配置配套后端父目录（该目录须含 OTAI/server.py）：'
               '\nPowerShell: $env:OTAI_ROOT="C:\\path\\to\\bundle"'
               '\nLinux/macOS: export OTAI_ROOT="/path/to/bundle"')


def fail(message):
    raise ValueError(message + '\n' + CONFIG_HELP)


def check_python(version=None):
    version = sys.version_info if version is None else version
    if tuple(version[:2]) != (3, 13):
        fail('此工具要求 Python 3.13.x；当前解释器为 ' + sys.executable +
             '，版本 ' + '.'.join(map(str, version[:3])) + '。请使用 Python 3.13 启动此脚本。')


def dependency_help(entry):
    requirements = str(entry.parent / 'requirements.txt')
    
    ps = lambda value: "'" + value.replace("'", "''") + "'"
    return ('\n请在同一 Python 3.13 解释器安装配套依赖（本工具不会自动安装）：'
            + '\nPowerShell: & ' + ps(sys.executable) + ' -m pip install -r ' + ps(requirements)
            + '\nLinux/macOS: ' + shlex.quote(sys.executable) + ' -m pip install -r ' + shlex.quote(requirements))


def check_dependencies(entry):
    expected = {'mcp': '1.29.0', 'pydantic': '2.13.4', 'fastapi': '0.141.1',
                'uvicorn': '0.52.1', 'jsonschema': '4.26.0'}
    problems = []
    unverified = []
    for package, wanted in expected.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            problems.append(package + ' 未安装')
            continue
        if package == 'pydantic' and actual.split('.')[0] != '2':
            problems.append('pydantic 当前 ' + actual + '，此工具要求 major 2 API')
        elif actual != wanted:
            unverified.append(package + ' 当前 ' + actual + '，已验证 ' + wanted)
    if problems:
        fail('配套依赖未就绪：' + '；'.join(problems) + dependency_help(entry))
    if unverified:
        print('依赖兼容性提示：以下版本尚未验证，将继续能力发现：' + '；'.join(unverified) + dependency_help(entry), file=sys.stderr)


def subprocess_environment(env=None):
    result = dict(os.environ if env is None else env)
    result['PYTHONIOENCODING'] = 'utf-8'
    result['PYTHONUTF8'] = '1'
    return result



class SoftwareAuthorizationBoundary(ValueError):
    def __init__(self,error):
        super().__init__(error['message']);self.error=error

def licensing_module(entry):
    """Refuse an older same-protocol backend without the mandatory gate."""
    folder=Path(entry).parent/'opentrack_ai'
    try:
        contract=json.loads((folder/'license_authorization_contract.json').read_text('utf-8'))
        if (contract.get('schema')!='opentrack-software-authorization-gate/1'
                or contract.get('authorization_gate_revision')!='full-license-attestation-1'
                or contract.get('required_original_license')!='full'):
            raise ValueError('Mismatched gate contract')
        import importlib.util
        spec=importlib.util.spec_from_file_location('paired_skill_software_authorization',folder/'license_authorization.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if (module.AUTHORIZATION_GATE_REVISION!='full-license-attestation-1'
                or module.REQUIRED_ORIGINAL_LICENSE!='full'):
            raise ValueError('Mismatched gate module')
    except (OSError,ValueError,ImportError,AttributeError) as exc:
        raise SoftwareAuthorizationBoundary({'code':'SOFTWARE_AUTHORIZATION_GATE_MISSING',
            'message':'The selected backend lacks the required full-software-licence confirmation gate. Use a matching paired backend with this mandatory guard; do not bypass it with a different installation.',
            'details':{'required_original_license':'full','authorization_gate_revision':'full-license-attestation-1'}}) from exc
    return module


def locate_backend(script, env):
    script = Path(script).resolve()
    if 'OTAI_ROOT' in env:
        if not env['OTAI_ROOT'].strip():
            fail('OTAI_ROOT 为空；不会回退到其他后端。')
        root = Path(env['OTAI_ROOT']).expanduser().resolve()
    else:
        skill = script.parent.parent
        ota = script.parents[3]
        if (ota.name == 'OTAI' and script == ota / 'skills' / 'opentrack-rail' / 'scripts' / 'ot.py'):
            root = ota.parent
        elif (script == skill / 'scripts' / 'ot.py'
              and (skill / 'backend' / 'OTAI' / 'server.py').is_file()):
            root = skill / 'backend'
        else:
            fail('未找到本 Skill 的配套后端；独立 Skill 须包含 backend/OTAI，不会向上搜索旧安装。')
    entry = root / 'OTAI' / 'server.py'
    if not entry.is_file():
        fail('指定目录缺少 OTAI/server.py；不会回退到旧后端。')
    version_path = root / 'OTAI' / 'opentrack_ai' / '__init__.py'
    try:
        tree = ast.parse(version_path.read_text(encoding='utf-8'))
        values = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets)]
    except (OSError, SyntaxError, ValueError, TypeError) as exc:
        fail('无法静态确认后端版本：' + str(exc))
    if values != [EXPECTED_VERSION]:
        fail(f'后端版本不兼容：检测到 {values!r}，要求 {EXPECTED_VERSION}；未执行该后端。')
    licensing_module(entry)
    return root, entry


def nonempty(value, label):
    if not value.strip():
        fail(label + ' 不能为空或只有空白。')
    return value


def parse_global_options(arguments):
    """Parse only global options, once; command payload remains opaque."""
    options = {}
    flags = []
    commands = ('call', 'tools', 'stdio', 'http')
    i = 0
    while i < len(arguments):
        token = arguments[i]
        if token in commands or token in ('--help', '-h'):
            return options, flags, arguments[i:]
        name, equals, value = token.partition('=')
        if name in ('--root', '--profile'):
            if name in options:
                fail(name + ' 重复；每个全局参数只能指定一次。')
            if not equals:
                i += 1
                if i >= len(arguments) or arguments[i].startswith('-') or arguments[i] in commands:
                    fail(name + ' 缺少值；请使用 ' + name + '=值。')
                value = arguments[i]
            options[name] = nonempty(value, name)
        elif token in ('--allow-apply', '--runtime-read'):
            flags.append(token)
        else:
            fail('无法识别全局参数或命令：' + token)
        i += 1
    return options, flags, []



def discover(entry, data_root, profile, *, env=None):
    try:
        result = subprocess.run([sys.executable, '-B', str(entry), '--root=' + data_root,
                                 '--profile=' + profile, 'tools'], capture_output=True,
                                text=True, encoding='utf-8', timeout=60, check=False,
                                env=subprocess_environment(env))
        if result.returncode:
            fail('配套后端工具发现失败：' + result.stderr[:1000] + result.stdout[:1000])
        body = json.loads(result.stdout)
        names = {item['name'] for item in body['tools']}
        if not all(isinstance(n, str) for n in names):
            raise ValueError('non-string tool name')
        return names
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        fail('无法校验配套后端工具清单：' + str(exc))


def main(arguments=None, *, script=None, env=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    env = os.environ if env is None else env
    try:
        check_python()
        options, flags, command_args = parse_global_options(arguments)
        root, entry = locate_backend(script or __file__, env)
        check_dependencies(entry)
        data_root = options['--root'] if '--root' in options else nonempty(env['OTAI_DATA_ROOT'], 'OTAI_DATA_ROOT') if 'OTAI_DATA_ROOT' in env else fail('必须显式提供 --root 或 OTAI_DATA_ROOT，指定实际数据根。')
        explicit_profile = options.get('--profile')
        profile = explicit_profile if explicit_profile is not None else nonempty(env['OTAI_PROFILE'], 'OTAI_PROFILE') if 'OTAI_PROFILE' in env else 'generation'
        if profile not in ('all', 'generation', 'simulation-evidence'):
            fail('未知 profile：' + profile)
        all_names = discover(entry, data_root, 'all', env=env)
        missing = REQUIRED_TOOLS - all_names
        if missing:
            fail('后端缺少所需接口：' + ', '.join(sorted(missing)))
        selected = all_names if profile == 'all' else discover(entry, data_root, profile, env=env)
        if command_args and command_args[0] == 'call':
            if len(command_args) < 2:
                fail('call 缺少工具名称。')
            requested = command_args[1]
            if requested not in all_names:
                fail('配套后端不存在请求工具：' + requested)
            if requested not in selected:
                if explicit_profile is None and 'OTAI_PROFILE' not in env:
                    profile = 'all'
                else:
                    fail('请求工具不在显式 profile 中：' + requested)
        if command_args and command_args[0]=='call' and len(command_args)>=2:
            gate=licensing_module(entry)
            if command_args[1] not in gate.METADATA_TOOLS:
                try:gate.require_authorization(data_root)
                except gate.SoftwareAuthorizationError as exc:
                    raise SoftwareAuthorizationBoundary(exc.as_dict()) from exc
        
        forwarded = ['--root=' + data_root, '--profile=' + profile] + flags + command_args
        return subprocess.call([sys.executable, '-B', str(entry), *forwarded], shell=False,
                               env=subprocess_environment(env))
    except SoftwareAuthorizationBoundary as exc:
        print(json.dumps({'ok':False,'error':exc.error},ensure_ascii=False))
        return 2
    except (ValueError, OSError) as exc:
        print('OpenTrack Skill 配置错误：' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

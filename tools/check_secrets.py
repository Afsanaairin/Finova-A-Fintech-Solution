"""Check Git history, index and non-ignored source without printing secrets.

Heuristic scan plus exact matching of locally configured AI/proxy credentials.
This does not replace provider-side secret scanning or credential rotation.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KEY_PATTERN = re.compile(rb'(?:hk_[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{20,})')
ASSIGNMENT = re.compile(
    rb'^[ \t]*(?:(?:export|const|let|var)[ \t]+)?(?:OPENAI_API_KEY|FINOVA_PROXY_TOKEN)'
    rb'[ \t]*[=:][ \t]*[\x27\x22]?([^\x27\x22\s,;<>`]+)', re.MULTILINE)


def placeholder(value):
    # Literal escaped newlines occur in the existing unit-test dotenv fixture.
    lower = value.lower().split(b'\\n', 1)[0]
    return (lower in (b'', b'`', b'api', b'none', b'null', b'config()', b'os.environ',
                      b'hk_from_file', b'hk_old_shell_key')
            or any(word in lower for word in (b'paste_your_', b'your_real_', b'replace_with_', b'hk_test_')))


def findings(blob, known=()):
    kinds = set()
    if any(not placeholder(match.group()) for match in KEY_PATTERN.finditer(blob)):
        kinds.add('credential-shaped value')
    if any(not placeholder(match.group(1)) for match in ASSIGNMENT.finditer(blob)):
        kinds.add('non-placeholder credential assignment')
    if any(secret in blob for secret in known):
        kinds.add('locally configured credential')
    if re.search(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----', blob):
        kinds.add('private key')
    return sorted(kinds)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def configured_credentials():
    # Read only for matching; never print values or load them into public assets.
    known = []
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_bytes().splitlines():
            name, separator, value = line.partition(b'=')
            value = value.strip().strip(b'\x27\x22')
            if separator and name.strip() in (b'OPENAI_API_KEY', b'FINOVA_PROXY_TOKEN'):
                if value and not placeholder(value):
                    known.append(value)
    return known


def main():
    known = configured_credentials()
    failed = False
    object_ids = {line.split()[0] for line in git('rev-list', '--objects', '--all').splitlines()}
    object_ids.update(line.split()[1] for line in git('ls-files', '--stage').splitlines())
    # Batch reads avoid one process per historic file. Print object IDs/kinds,
    # never matching lines, upstream bodies, or credential bytes.
    process = subprocess.Popen(['git', '-C', str(ROOT), 'cat-file', '--batch'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for oid in sorted(object_ids):
            process.stdin.write(oid + b'\n')
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3:
                raise RuntimeError('Could not inspect a Git object.')
            size = int(header[2])
            blob = process.stdout.read(size)
            process.stdout.read(1)
            if header[1] in (b'blob', b'commit', b'tag'):
                kinds = findings(blob, known)
                if kinds:
                    print('Potential secret in Git', header[1].decode(), oid.decode()[:12] + ':', ', '.join(kinds))
                    failed = True
    finally:
        process.stdin.close()
        process.stdout.close()
        process.wait()
    paths = [path.decode('utf-8') for path in git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\x00') if path]
    for path in paths:
        file = ROOT / path
        if file.is_file():
            kinds = findings(file.read_bytes(), known)
            if kinds:
                print('Potential secret in source file', path + ':', ', '.join(kinds))
                failed = True
    if failed:
        print('Do not publish these values. Review privately; rotate any exposed credential before history cleanup.')
        return 1
    print(f'No matching secrets found in {len(object_ids)} Git objects and {len(paths)} non-ignored source files.')
    print('Heuristic scan only; keep provider/GitHub secret scanning enabled.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Validate sources, stage documents, and build this repository independently."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.build'
DOCS = BUILD / 'docs'


def sources():
    return sorted(p for p in ROOT.rglob('*.md')
                  if not any(part.startswith('.') for part in p.relative_to(ROOT).parts))


def check():
    errors = []
    docs = sources()
    for doc in docs:
        text = doc.read_text(encoding='utf-8')
        text = re.sub(r'(?ms)^```.*?^```\s*$', '', text)
        headings = re.findall(r'(?m)^(#{1,6}) ', text)
        if headings.count('#') != 1:
            errors.append(f'{doc.relative_to(ROOT)}: expected one H1')
        previous = 0
        for heading in headings:
            if len(heading) > previous + 1:
                errors.append(f'{doc.relative_to(ROOT)}: skipped heading level')
            previous = len(heading)
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (doc.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(ROOT):
                errors.append(f'{doc.relative_to(ROOT)}: link escapes repository: {target}')
            elif not resolved.is_file():
                errors.append(f'{doc.relative_to(ROOT)}: missing link: {target}')
    manifest = json.loads((ROOT / 'assets/image-manifest.json').read_text(encoding='utf-8'))
    expected = set()
    for image in manifest['images']:
        file = ROOT / image['path']
        expected.add(file.resolve())
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != image['sha256']:
            errors.append(f"image changed or missing: {image['path']}")
    actual = {p.resolve() for p in ROOT.rglob('*') if p.is_file()
              and not any(s.startswith('.') for s in p.relative_to(ROOT).parts)
              and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}}
    if actual != expected:
        errors.append('image files do not match the manifest')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Validated {len(docs)} Markdown files and {len(expected)} images.', flush=True)


def callouts(text):
    lines = text.splitlines()
    result, index, fenced = [], 0, False
    while index < len(lines):
        line = lines[index]
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
        match = re.fullmatch(r'> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]', line) if not fenced else None
        if match:
            kind = {'IMPORTANT': 'info', 'CAUTION': 'danger'}.get(match[1], match[1].lower())
            result.extend(['', f'!!! {kind} "{match[1].title()}"'])
            index += 1
            while index < len(lines) and lines[index].startswith('>'):
                result.append('    ' + re.sub(r'^> ?', '', lines[index]))
                index += 1
            result.append('')
        else:
            result.append(line)
            index += 1
    return '\n'.join(result) + '\n'


def stage():
    # Remove only the generated directory after confirming its exact location.
    if DOCS.resolve().parent != BUILD.resolve() or not BUILD.resolve().is_relative_to(ROOT):
        raise SystemExit('Unsafe build path')
    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True)
    for doc in sources():
        dest = DOCS / doc.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(callouts(doc.read_text(encoding='utf-8')), encoding='utf-8')
    for directory in ['assets', '代码']:
        src = ROOT / directory
        if src.is_dir():
            shutil.copytree(src, DOCS / directory, ignore=shutil.ignore_patterns('image-manifest.json'))
    if (ROOT / 'LICENSE').exists():
        shutil.copy2(ROOT / 'LICENSE', DOCS / 'LICENSE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'check'], nargs='?', default='build')
    args = parser.parse_args()
    check()
    if args.command == 'check':
        return
    stage()
    cmd = [sys.executable, '-m', 'mkdocs', args.command, '--strict', '--config-file', str(ROOT / 'mkdocs.yml')]
    subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()

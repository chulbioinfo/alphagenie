"""Run from the cloned repository: python -m alphagenie --help."""
import argparse
import getpass
import json
import os
import shutil
import sys

from .config import private_write, read_config, state_dir, key_available, save_config


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="AlphaGENIE local: v0.23 UI / v0.20 engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Local installation checks; never contacts the API")
    key = sub.add_parser("key", help="Manage your local key without echo or command-line arguments")
    key.add_argument("action", choices=["set", "delete", "status"])
    configure = sub.add_parser("configure", help="Set paths to your GRCh38 FASTA, FAI and GENCODE GTF")
    configure.add_argument("--fasta", required=True)
    configure.add_argument("--gtf", required=True)
    configure.add_argument("--samtools", default=shutil.which("samtools"))
    serve = sub.add_parser("serve", help="Open the local-only application; Ctrl+C stops active jobs")
    serve.add_argument("--port", type=int, default=8877)
    worker = sub.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("job_id")
    worker.add_argument("--lock-fd", type=int, required=True)
    args = parser.parse_args()
    if args.command == "key":
        path = state_dir() / "credentials.json"
        if args.action == "set":
            if not sys.stdin.isatty():
                raise ValueError("Use an interactive terminal; piped credential input is not accepted")
            value = getpass.getpass("Your AlphaGenome API key (hidden): ").strip()
            if not 16 <= len(value) <= 512 or any(c.isspace() for c in value):
                raise ValueError("Invalid API key format")
            private_write(path, json.dumps({"api_key": value}) + "\n")
            print("Key saved locally with owner-only permissions. Not encrypted; not uploaded to AlphaGENIE.")
        elif args.action == "delete":
            if path.is_symlink():
                raise ValueError("Refusing a symlink credential target")
            if path.exists():
                path.unlink()
                print("Local credential file deleted (not securely erased from backups). Unset any environment key separately.")
            else:
                print("No credential file exists. Unset any environment key separately.")
        else:
            print("Key configured: " + str(key_available()) + " (value never displayed)")
    elif args.command == "configure":
        if not args.samtools:
            raise ValueError("Install samtools or pass --samtools /path/to/samtools")
        save_config(args.fasta, args.gtf, args.samtools)
        print("Reference paths saved locally. No API request made.")
    elif args.command == "doctor":
        from importlib.metadata import version
        from .validation import validate_references
        from app.manuscript_release import manifest
        print("Python:", sys.version.split()[0], "| AlphaGenome SDK:", version("alphagenome"))
        print("Frozen v0.20 release:", manifest()["release_id"], "— hashes verified")
        print("Key configured:", key_available(), "(not tested against provider)")
        try:
            validate_references(read_config())
            print("Reference files: configured; sequence checks happen before each job")
        except ValueError:
            print("Reference files: not ready. Saved-result browsing still works.")
        print("No network request made. State:", state_dir())
    elif args.command == "serve":
        if not 1024 <= args.port <= 65535:
            raise ValueError("Use a port between 1024 and 65535")
        import uvicorn
        from .server import create_app
        print(f"Open http://127.0.0.1:{args.port}/ — keep this terminal open. No public hosting.")
        print("No login: other local programs or OS users may access local analyses. Use a trusted, single-user computer.")
        uvicorn.run(create_app(args.port), host="127.0.0.1", port=args.port, proxy_headers=False,
                    access_log=False, log_level="warning")
    elif args.command == "_worker":
        from .runner import execute_worker
        execute_worker(args.job_id, args.lock_fd)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        from .security import redact
        print("Error:", redact(str(exc)), file=sys.stderr)
        sys.exit(1)

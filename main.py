from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from foa_extract.exporter import export_all
from foa_extract.ingestor import ingest
from foa_extract.tagger import apply_tags


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="foa-extract",
        description="Extract and tag Funding Opportunity Announcements from Grants.gov and NSF",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL of the Grants.gov or NSF opportunity page",
    )
    parser.add_argument(
        "--out-dir",
        default="./out",
        help="Output directory for JSON/CSV files (default: ./out)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "all"],
        default="all",
        help="Output format: json, csv, or all (default: all)",
    )
    parser.add_argument(
        "--no-nlp",
        action="store_true",
        help="Disable TF-IDF NLP tagging (use keyword matching only)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    log = logging.getLogger(__name__)

    log.info("URL: %s", args.url)
    log.info("Output directory: %s", Path(args.out_dir).resolve())
    log.info("Format: %s", args.format)
    log.info("NLP tagging: %s", "disabled" if args.no_nlp else "enabled")

    try:
        log.info("Extracting metadata...")
        opportunity = ingest(args.url)
        log.info("Title: %s", opportunity.title)
        log.info("Agency: %s", opportunity.agency)
        log.info("FOA ID: %s", opportunity.foa_id)

        log.info("Applying tags...")
        use_nlp = not args.no_nlp
        tags = apply_tags(opportunity.title, opportunity.description, use_nlp=use_nlp)
        opportunity.tags = tags
        log.info("Tags: %s", ", ".join(tags) if tags else "none")

        log.info("Exporting results...")
        formats = [args.format] if args.format != "all" else ["json", "csv"]
        results = export_all(opportunity, args.out_dir, formats=formats)
        for fmt, path in results.items():
            log.info("%s -> %s", fmt.upper(), path.resolve())

        log.info("Done.")
        return 0

    except ValueError as exc:
        log.error("Validation error: %s", exc)
        return 1

    except ConnectionError as exc:
        log.error("Connection error: %s", exc)
        return 2

    except Exception as exc:
        log.exception("Unexpected error: %s", exc)
        return 3


if __name__ == "__main__":
    sys.exit(main())

"""CLI runner for the Interior Architect Agent Team."""
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(
        description="Interior Architect Agent Team (Gemini + Claude)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_team.py "5x4m industrial office with desk and chair"
  python run_team.py "living room 6x4, add office desk and armchair" --llm claude
  python run_team.py --serve
        """,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Design request in natural language",
    )
    parser.add_argument(
        "--llm",
        choices=["gemini", "claude"],
        default="gemini",
        help="LLM backend to use (default: gemini)",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start FastAPI server on http://localhost:8080 for the HTML UI",
    )

    args = parser.parse_args()

    if args.serve:
        import uvicorn
        print("=" * 60)
        print("Interior Design API starting...")
        print("API:  http://localhost:8080")
        print("Docs: http://localhost:8080/docs")
        print("Open prompt_builder.html in your browser.")
        print("=" * 60)
        uvicorn.run("agents.api:app", host="0.0.0.0", port=8080, reload=False)

    elif args.prompt:
        from agents.team import run_team
        print(f"\nLLM: {args.llm.upper()}")
        print("=" * 60)
        result = run_team(args.prompt, llm=args.llm)
        print(result)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

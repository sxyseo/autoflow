#!/usr/bin/env python3
"""
Autoflow Quality Prediction CLI Tool

Command-line tool for predicting code quality from spec characteristics.
Uses trained ML models to predict potential quality issues before implementation.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoflow.prediction.model import PredictionResult
from autoflow.prediction.predictor import QualityPredictor


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="predict_quality.py",
        description="Autoflow quality prediction tool for spec-based quality assessment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --spec .auto-claude/specs/020-ai-code-quality-prediction
                                     Predict quality for a spec
  %(prog)s --spec ./spec-dir --explain
                                     Show detailed prediction with explanation
  %(prog)s --spec ./spec-dir --output json
                                     Output prediction as JSON
  %(prog)s --model-path /path/to/model.pkl --spec ./spec-dir
                                     Use custom model file
  %(prog)s --spec ./spec-dir --create-review
                                     Create review task if high-risk
        """,
    )

    parser.add_argument(
        "--spec",
        "-s",
        type=Path,
        help="Path to spec directory containing implementation_plan.json",
    )

    parser.add_argument(
        "--model-path",
        "-m",
        type=Path,
        help="Path to trained model file (default: .autoflow/models/quality_model.pkl)",
    )

    parser.add_argument(
        "--explain",
        "-e",
        action="store_true",
        help="Show detailed prediction explanation with feature importances",
    )

    parser.add_argument(
        "--output",
        "-o",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--create-review",
        action="store_true",
        help="Create review task in implementation plan if high-risk prediction",
    )

    parser.add_argument(
        "--allow-untrained",
        action="store_true",
        help="Allow using an untrained model (for testing only)",
    )

    parser.add_argument(
        "--work-dir",
        "-w",
        type=Path,
        default=".",
        help="Working directory (default: .)",
    )

    parser.add_argument(
        "--train",
        action="store_true",
        help="Train a new model (requires --data-dir, use train_model.py instead)",
    )

    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Evaluate model performance (use train_model.py instead)",
    )

    return parser.parse_args()


def print_prediction_text(
    prediction: PredictionResult, spec_path: Path, explain: bool = False
) -> None:
    """
    Print prediction result in human-readable text format.

    Args:
        prediction: PredictionResult to display
        spec_path: Path to the spec (for context)
        explain: Whether to show detailed explanation
    """
    # Determine risk level and symbol
    if prediction.confidence >= 0.8:
        risk_symbol = "✅"
        risk_label = "LOW RISK"
    elif prediction.confidence >= 0.6:
        risk_symbol = "⚠️ "
        risk_label = "MEDIUM RISK"
    else:
        risk_symbol = "🔴"
        risk_label = "HIGH RISK"

    # Print header
    print("\n" + "=" * 70)
    print("QUALITY PREDICTION REPORT")
    print("=" * 70)
    print(f"\nSpec: {spec_path}")
    print(f"Status: {risk_symbol} {prediction.prediction.value.upper()}")
    print(f"Confidence: {prediction.confidence:.2%}")
    print(f"Risk Level: {risk_label}")

    # Print rationale if available
    if prediction.rationale:
        print("\nRationale:")
        print(f"  {prediction.rationale}")

    # Print feature importances if explain mode
    if explain and prediction.feature_importances:
        print("\nTop Feature Importances:")
        # Sort by importance and show top 5
        sorted_features = sorted(
            prediction.feature_importances.items(), key=lambda x: x[1], reverse=True
        )[:5]

        for feature, importance in sorted_features:
            bar = "█" * int(importance * 40)
            print(f"  {feature:30s} {importance:6.3f} {bar}")

    print("\n" + "=" * 70)


def print_prediction_json(prediction: PredictionResult, spec_path: Path) -> None:
    """
    Print prediction result in JSON format.

    Args:
        prediction: PredictionResult to display
        spec_path: Path to the spec (for context)
    """
    result = {
        "spec_path": str(spec_path),
        "prediction": prediction.prediction.value,
        "confidence": prediction.confidence,
        "rationale": prediction.rationale,
        "feature_importances": prediction.feature_importances,
        "is_high_risk": prediction.confidence < 0.6
        or prediction.prediction.value in ["needs_changes", "failed"],
    }

    print(json.dumps(result, indent=2))


def predict_for_spec(
    spec_path: Path,
    model_path: Path | None,
    work_dir: Path,
    allow_untrained: bool,
    explain: bool,
    output_format: str,
    create_review: bool,
) -> int:
    """
    Run quality prediction for a spec.

    Args:
        spec_path: Path to spec directory
        model_path: Optional path to model file
        work_dir: Working directory
        allow_untrained: Whether to allow untrained models
        explain: Whether to show detailed explanation
        output_format: Output format (text or json)
        create_review: Whether to create review task if high-risk

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Validate spec path
    if not spec_path.exists():
        print(f"Error: Spec path does not exist: {spec_path}", file=sys.stderr)
        return 1

    plan_file = spec_path / "implementation_plan.json"
    if not plan_file.exists():
        print(f"Error: Implementation plan not found: {plan_file}", file=sys.stderr)
        return 1

    try:
        # Initialize predictor
        predictor = QualityPredictor(
            model_path=model_path, root_dir=work_dir, allow_untrained=allow_untrained
        )

        # Check if model is trained
        if not allow_untrained and predictor.model.model is None:
            print(
                "Error: Model is not trained. Please train the model first using scripts/train_model.py",
                file=sys.stderr,
            )
            return 1

        # Run prediction
        prediction = predictor.predict_spec(spec_path)

        # Output prediction
        if output_format == "json":
            print_prediction_json(prediction, spec_path)
        else:
            print_prediction_text(prediction, spec_path, explain=explain)

        # Create review task if requested and high-risk
        if create_review:
            if predictor.is_high_risk(prediction):
                try:
                    created = predictor.create_review_task(spec_path, prediction)
                    if created:
                        print("\n✓ Created review task in implementation plan")
                    else:
                        print("\n⚠ Review task not created (prediction not high-risk)")
                except Exception as e:
                    print(
                        f"\n⚠ Warning: Failed to create review task: {e}",
                        file=sys.stderr,
                    )
            else:
                print("\n⚠ Review task not created (prediction is low-risk)")

        # Return exit code based on prediction
        # Return 1 if high-risk (needs_changes or failed), 0 if success
        if prediction.prediction.value in ["needs_changes", "failed"]:
            return 1
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """
    Main entry point for quality prediction CLI.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()

    # Handle deprecated train/evaluate options
    if args.train or args.evaluate:
        print("Error: --train and --evaluate options are deprecated.", file=sys.stderr)
        print(
            "Please use scripts/train_model.py for training and evaluation.",
            file=sys.stderr,
        )
        return 1

    # Require spec path
    if not args.spec:
        print("Error: --spec is required", file=sys.stderr)
        print("\nUse --help to see usage information", file=sys.stderr)
        return 1

    # Run prediction
    return predict_for_spec(
        spec_path=args.spec,
        model_path=args.model_path,
        work_dir=args.work_dir,
        allow_untrained=args.allow_untrained,
        explain=args.explain,
        output_format=args.output,
        create_review=args.create_review,
    )


if __name__ == "__main__":
    sys.exit(main())

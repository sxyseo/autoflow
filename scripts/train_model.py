#!/usr/bin/env python3
"""
Autoflow Model Training CLI Tool

Command-line tool for training and evaluating ML models for code quality prediction.
Collects historical data, trains a model, and evaluates performance.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoflow.prediction.data_collector import DataCollector
from autoflow.prediction.model import QualityModel

try:
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="train_model.py",
        description="Autoflow model training tool for quality prediction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --data-dir .autoflow/runs
                                     Train model with historical run data
  %(prog)s --data-dir .autoflow/runs --evaluate
                                     Train and evaluate model performance
  %(prog)s --data-dir .autoflow/runs --output json
                                     Output training results as JSON
  %(prog)s --data-dir .autoflow/runs --model-path /path/to/model.pkl
                                     Save model to custom path
  %(prog)s --data-dir .autoflow/runs --test-split 0.3
                                     Use 30%% of data for testing
  %(prog)s --evaluate-only --model-path .autoflow/models/quality_model.pkl
                                     Evaluate existing model without training
        """
    )

    parser.add_argument(
        "--data-dir",
        "-d",
        type=Path,
        help="Path to directory containing run JSON files (default: .autoflow/runs)"
    )

    parser.add_argument(
        "--specs-dir",
        type=Path,
        help="Path to directory containing spec directories (default: .auto-claude/specs/)"
    )

    parser.add_argument(
        "--model-path",
        "-m",
        type=Path,
        help="Path to save/load model file (default: .autoflow/models/quality_model.pkl)"
    )

    parser.add_argument(
        "--output",
        "-o",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    parser.add_argument(
        "--evaluate",
        "-e",
        action="store_true",
        help="Evaluate model performance after training"
    )

    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Evaluate existing model without training (requires --model-path)"
    )

    parser.add_argument(
        "--test-split",
        "-t",
        type=float,
        default=0.2,
        help="Fraction of data to use for testing (default: 0.2)"
    )

    parser.add_argument(
        "--n-estimators",
        type=int,
        default=100,
        help="Number of trees in random forest (default: 100)"
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum depth of trees (default: unlimited)"
    )

    parser.add_argument(
        "--work-dir",
        "-w",
        type=Path,
        default=".",
        help="Working directory (default: .)"
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force training even with minimal data"
    )

    return parser.parse_args()


def print_training_summary_text(
    num_samples: int,
    num_features: int,
    model_path: Path
) -> None:
    """
    Print training summary in human-readable text format.

    Args:
        num_samples: Number of training samples
        num_features: Number of features
        model_path: Path where model was saved
    """
    print("\n" + "=" * 70)
    print("MODEL TRAINING SUMMARY")
    print("=" * 70)
    print(f"\nTraining Samples: {num_samples}")
    print(f"Features: {num_features}")
    print(f"Model Saved: {model_path}")
    print("\n" + "=" * 70)


def print_evaluation_results_text(
    report: dict,
    confusion_matrix_data: list,
    test_size: int
) -> None:
    """
    Print evaluation results in human-readable text format.

    Args:
        report: Classification report dictionary
        confusion_matrix_data: Confusion matrix
        test_size: Number of test samples
    """
    print("\n" + "=" * 70)
    print("MODEL EVALUATION RESULTS")
    print("=" * 70)
    print(f"\nTest Samples: {test_size}")
    print("\nClassification Report:")

    # Print classification report in formatted way
    for label, metrics in report.items():
        if label == "accuracy":
            print(f"\n  Accuracy: {metrics:.3f}")
        else:
            print(f"\n  Class: {label}")
            print(f"    Precision: {metrics.get('precision', 0):.3f}")
            print(f"    Recall: {metrics.get('recall', 0):.3f}")
            print(f"    F1-score: {metrics.get('f1-score', 0):.3f}")
            print(f"    Support: {metrics.get('support', 0)}")

    print("\nConfusion Matrix:")
    print("  Predicted:")
    print("           Success  Issues")
    for i, row in enumerate(confusion_matrix_data):
        actual = "Success" if i == 0 else "Issues"
        print(f"  Actual: {actual:8s} {row}")

    print("\n" + "=" * 70)


def print_training_results_json(
    num_samples: int,
    num_features: int,
    model_path: Path,
    evaluation_results: dict | None = None
) -> None:
    """
    Print training results in JSON format.

    Args:
        num_samples: Number of training samples
        num_features: Number of features
        model_path: Path where model was saved
        evaluation_results: Optional evaluation results dict
    """
    result = {
        "training_samples": num_samples,
        "num_features": num_features,
        "model_path": str(model_path),
        "status": "success"
    }

    if evaluation_results:
        result["evaluation"] = evaluation_results

    print(json.dumps(result, indent=2))


def train_model(
    data_dir: Path,
    specs_dir: Path | None,
    model_path: Path | None,
    work_dir: Path,
    test_split: float,
    n_estimators: int,
    max_depth: int | None,
    evaluate: bool,
    force: bool,
    output_format: str
) -> int:
    """
    Train a quality prediction model.

    Args:
        data_dir: Path to directory containing run JSON files
        specs_dir: Optional path to specs directory
        model_path: Optional path to save model
        work_dir: Working directory
        test_split: Fraction of data for testing
        n_estimators: Number of trees in random forest
        max_depth: Maximum depth of trees
        evaluate: Whether to evaluate model
        force: Force training even with minimal data
        output_format: Output format (text or json)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Validate data directory
    if not data_dir.exists():
        print(f"Error: Data directory does not exist: {data_dir}", file=sys.stderr)
        return 1

    try:
        # Collect training data
        print("Collecting training data...")
        collector = DataCollector(root_dir=work_dir)

        feature_dicts, outcome_labels = collector.collect_training_data_for_model(
            runs_dir=data_dir,
            specs_dir=specs_dir
        )

        num_samples = len(feature_dicts)

        if num_samples == 0:
            print("Error: No training data found. Please ensure you have completed runs in the data directory.", file=sys.stderr)
            return 1

        if num_samples < 10 and not force:
            print(f"Error: Insufficient training data ({num_samples} samples). Minimum 10 samples required.", file=sys.stderr)
            print("Use --force to train anyway (not recommended).", file=sys.stderr)
            return 1

        print(f"Found {num_samples} training samples")

        # Train model
        print("Training model...")
        model = QualityModel(
            n_estimators=n_estimators,
            max_depth=max_depth
        )

        evaluation_results = None

        if evaluate and SKLEARN_AVAILABLE and num_samples >= 10:
            # Split data for evaluation
            X_train, X_test, y_train, y_test = train_test_split(
                feature_dicts,
                outcome_labels,
                test_size=test_split,
                random_state=42,
                stratify=outcome_labels
            )

            # Train on training set
            model.train(X_train, y_train)

            # Evaluate on test set
            print("Evaluating model...")
            y_pred = []
            for features in X_test:
                result = model.predict(features)
                y_pred.append(result.prediction.value)

            # Generate classification report
            report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
            cm = confusion_matrix(y_test, y_pred, labels=["success", "issues"])

            evaluation_results = {
                "classification_report": report,
                "confusion_matrix": cm.tolist(),
                "test_size": len(X_test)
            }

            # Re-train on full dataset
            print("Re-training on full dataset...")
            model.train(feature_dicts, outcome_labels)

        else:
            # Train on full dataset
            model.train(feature_dicts, outcome_labels)

        # Save model
        print("Saving model...")
        saved_path = model.save(model_path)

        # Output results
        if output_format == "json":
            print_training_results_json(
                num_samples=num_samples,
                num_features=len(model.feature_names),
                model_path=saved_path,
                evaluation_results=evaluation_results
            )
        else:
            print_training_summary_text(
                num_samples=num_samples,
                num_features=len(model.feature_names),
                model_path=saved_path
            )

            if evaluation_results:
                print_evaluation_results_text(
                    report=evaluation_results["classification_report"],
                    confusion_matrix_data=evaluation_results["confusion_matrix"],
                    test_size=evaluation_results["test_size"]
                )

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def evaluate_model_only(
    model_path: Path,
    data_dir: Path,
    specs_dir: Path | None,
    work_dir: Path,
    test_split: float,
    output_format: str
) -> int:
    """
    Evaluate an existing model without training.

    Args:
        model_path: Path to model file
        data_dir: Path to directory containing run JSON files
        specs_dir: Optional path to specs directory
        work_dir: Working directory
        test_split: Fraction of data for testing
        output_format: Output format (text or json)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Validate model path
    if not model_path.exists():
        print(f"Error: Model file does not exist: {model_path}", file=sys.stderr)
        return 1

    if not SKLEARN_AVAILABLE:
        print("Error: scikit-learn is required for evaluation. Install with: pip install scikit-learn", file=sys.stderr)
        return 1

    try:
        # Load model
        print("Loading model...")
        model = QualityModel.load(model_path)

        if not model.is_trained:
            print("Error: Model is not trained", file=sys.stderr)
            return 1

        # Collect evaluation data
        print("Collecting evaluation data...")
        collector = DataCollector(root_dir=work_dir)

        feature_dicts, outcome_labels = collector.collect_training_data_for_model(
            runs_dir=data_dir,
            specs_dir=specs_dir
        )

        num_samples = len(feature_dicts)

        if num_samples == 0:
            print("Error: No evaluation data found.", file=sys.stderr)
            return 1

        if num_samples < 10:
            print(f"Warning: Limited evaluation data ({num_samples} samples). Results may not be reliable.", file=sys.stderr)

        print(f"Found {num_samples} evaluation samples")

        # Use all data for evaluation
        print("Evaluating model...")
        y_pred = []
        for features in feature_dicts:
            result = model.predict(features)
            y_pred.append(result.prediction.value)

        # Generate classification report
        report = classification_report(outcome_labels, y_pred, output_dict=True, zero_division=0)
        cm = confusion_matrix(outcome_labels, y_pred, labels=["success", "issues"])

        evaluation_results = {
            "classification_report": report,
            "confusion_matrix": cm.tolist(),
            "test_size": num_samples
        }

        # Output results
        if output_format == "json":
            result = {
                "model_path": str(model_path),
                "evaluation": evaluation_results,
                "status": "success"
            }
            print(json.dumps(result, indent=2))
        else:
            print_evaluation_results_text(
                report=report,
                confusion_matrix_data=cm.tolist(),
                test_size=num_samples
            )

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """
    Main entry point for model training CLI.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()

    # Handle evaluate-only mode
    if args.evaluate_only:
        if not args.model_path:
            print("Error: --model-path is required for --evaluate-only", file=sys.stderr)
            print("\nUse --help to see usage information", file=sys.stderr)
            return 1

        # Use provided data_dir or default
        data_dir = args.data_dir or Path(args.work_dir) / ".autoflow" / "runs"

        return evaluate_model_only(
            model_path=args.model_path,
            data_dir=data_dir,
            specs_dir=args.specs_dir,
            work_dir=args.work_dir,
            test_split=args.test_split,
            output_format=args.output
        )

    # Require data directory for training
    if not args.data_dir:
        print("Error: --data-dir is required for training", file=sys.stderr)
        print("\nUse --help to see usage information", file=sys.stderr)
        return 1

    # Train model
    return train_model(
        data_dir=args.data_dir,
        specs_dir=args.specs_dir,
        model_path=args.model_path,
        work_dir=args.work_dir,
        test_split=args.test_split,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        evaluate=args.evaluate,
        force=args.force,
        output_format=args.output
    )


if __name__ == "__main__":
    sys.exit(main())

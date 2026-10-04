"""Exports the Pydantic event models to packages/schema as JSON Schema."""

import json
import os
from pathlib import Path
from typing import Dict, Any
from pydantic import BaseModel, TypeAdapter

# Import all event models
from mux.events.models import (
    EventType,
    BaseEvent,
    RoomCreatedEvent,
    RoomJoinedEvent,
    RoomLeftEvent,
    RoomClosedEvent,
    RoomSharingUpdatedEvent,
    UserJoinedEvent,
    UserLeftEvent,
    UserTypingEvent,
    UserPresenceChangedEvent,
    PlanCreatedEvent,
    PlanUpdatedEvent,
    PlanItemAddedEvent,
    PlanItemUpdatedEvent,
    PlanItemRemovedEvent,
    PlanItemCompletedEvent,
    UserMessageSentEvent,
    AIMessageStartedEvent,
    AIMessageChunkEvent,
    AIMessageCompletedEvent,
    CommandSteerEvent,
    CommandVoteEvent,
    CommandOverrideEvent,
    CommandApprovePlanEvent,
    CommandEditPlanEvent,
    CommandAnswerQuestionEvent,
    CommandRewindEvent,
    CommandEndSessionEvent,
    FileCreatedEvent,
    FileUpdatedEvent,
    FileDeletedEvent,
    FileRenamedEvent,
    CheckpointCreatedEvent,
    CheckpointRestoredEvent,
    ConflictDetectedEvent,
    ConflictResolvedEvent,
    QuestionAskedEvent,
    QuestionAnsweredEvent,
    GithubSyncStartedEvent,
    GithubSyncCompletedEvent,
    TavilySearchCompletedEvent,
    SystemErrorEvent,
    SystemWarningEvent,
    SittingEndedEvent,
    BudgetExceededEvent,
    TaskStartedEvent,
    TaskFinishedEvent,
)


def generate_schemas(output_dir: str = "schemas") -> Dict[str, Any]:
    """
    Generate JSON Schema files for all event models.

    Args:
        output_dir: Directory to save schema files (default: "schemas")

    Returns:
        Dictionary mapping model names to their schema dictionaries
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Collect all models to export
    models_to_export = {
        "EventType": EventType,
        "BaseEvent": BaseEvent,
        "RoomCreatedEvent": RoomCreatedEvent,
        "RoomJoinedEvent": RoomJoinedEvent,
        "RoomLeftEvent": RoomLeftEvent,
        "RoomClosedEvent": RoomClosedEvent,
        "RoomSharingUpdatedEvent": RoomSharingUpdatedEvent,
        "UserJoinedEvent": UserJoinedEvent,
        "UserLeftEvent": UserLeftEvent,
        "UserTypingEvent": UserTypingEvent,
        "UserPresenceChangedEvent": UserPresenceChangedEvent,
        "PlanCreatedEvent": PlanCreatedEvent,
        "PlanUpdatedEvent": PlanUpdatedEvent,
        "PlanItemAddedEvent": PlanItemAddedEvent,
        "PlanItemUpdatedEvent": PlanItemUpdatedEvent,
        "PlanItemRemovedEvent": PlanItemRemovedEvent,
        "PlanItemCompletedEvent": PlanItemCompletedEvent,
        "UserMessageSentEvent": UserMessageSentEvent,
        "AIMessageStartedEvent": AIMessageStartedEvent,
        "AIMessageChunkEvent": AIMessageChunkEvent,
        "AIMessageCompletedEvent": AIMessageCompletedEvent,
        "CommandSteerEvent": CommandSteerEvent,
        "CommandVoteEvent": CommandVoteEvent,
        "CommandOverrideEvent": CommandOverrideEvent,
        "CommandApprovePlanEvent": CommandApprovePlanEvent,
        "CommandEditPlanEvent": CommandEditPlanEvent,
        "CommandAnswerQuestionEvent": CommandAnswerQuestionEvent,
        "CommandRewindEvent": CommandRewindEvent,
        "CommandEndSessionEvent": CommandEndSessionEvent,
        "FileCreatedEvent": FileCreatedEvent,
        "FileUpdatedEvent": FileUpdatedEvent,
        "FileDeletedEvent": FileDeletedEvent,
        "FileRenamedEvent": FileRenamedEvent,
        "CheckpointCreatedEvent": CheckpointCreatedEvent,
        "CheckpointRestoredEvent": CheckpointRestoredEvent,
        "ConflictDetectedEvent": ConflictDetectedEvent,
        "ConflictResolvedEvent": ConflictResolvedEvent,
        "QuestionAskedEvent": QuestionAskedEvent,
        "QuestionAnsweredEvent": QuestionAnsweredEvent,
        "GithubSyncStartedEvent": GithubSyncStartedEvent,
        "GithubSyncCompletedEvent": GithubSyncCompletedEvent,
        "TavilySearchCompletedEvent": TavilySearchCompletedEvent,
        "SystemErrorEvent": SystemErrorEvent,
        "SystemWarningEvent": SystemWarningEvent,
        "SittingEndedEvent": SittingEndedEvent,
        "BudgetExceededEvent": BudgetExceededEvent,
        "TaskStartedEvent": TaskStartedEvent,
        "TaskFinishedEvent": TaskFinishedEvent,
    }

    # Generate schema for each model
    schemas = {}
    for name, model in models_to_export.items():
        try:
            # Generate JSON Schema (TypeAdapter also handles the EventType enum)
            schema = TypeAdapter(model).json_schema()

            # Add some metadata
            schema["title"] = name
            schema["description"] = f"JSON Schema for {name} event model"

            # Save to file
            schema_file = output_path / f"{name}.schema.json"
            with open(schema_file, "w", encoding="utf-8") as f:
                json.dump(schema, f, indent=2, ensure_ascii=False)

            schemas[name] = schema
            print(f"✓ Generated schema for {name} -> {schema_file}")

        except Exception as e:
            print(f"✗ Failed to generate schema for {name}: {e}")

    # Also generate a combined schema file with all definitions
    combined_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "MUX Event Schemas",
        "description": "JSON Schemas for all MUX event models",
        "type": "object",
        "oneOf": [
            {"$ref": f"#/definitions/{name}"}
            for name in schemas.keys()
        ],
        "definitions": schemas,
    }

    combined_file = output_path / "all-events.schema.json"
    with open(combined_file, "w", encoding="utf-8") as f:
        json.dump(combined_schema, f, indent=2, ensure_ascii=False)

    print(f"✓ Generated combined schema -> {combined_file}")

    return schemas


def main():
    """Main entry point for the script."""
    print("Generating JSON Schema files from Pydantic models...")
    print("=" * 50)

    # Generate schemas in the schemas directory relative to this script
    script_dir = Path(__file__).parent
    schemas_dir = script_dir / "schemas"

    schemas = generate_schemas(str(schemas_dir))

    print("=" * 50)
    print(f"Generated {len(schemas)} individual schema files")
    print(f"Plus 1 combined schema file")
    print(f"All schemas saved to: {schemas_dir}")
    print("\nNext steps:")
    print("1. Use these JSON Schema files for validation")
    print("2. Generate TypeScript types using tools like:")
    print("   - json-schema-to-typescript")
    print("   - @json-schema-tools/generator-ts")
    print("   - Or similar JSON Schema to TypeScript converters")


if __name__ == "__main__":
    main()
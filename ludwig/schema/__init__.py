#
# Module structure:
# ludwig.schema               <-- Meant to contain all schemas, utilities, helpers related to describing and validating
#                                 Ludwig configs.
# ├── __init__.py             <-- Contains fully assembled Ludwig schema (`get_schema()`), `validate_config()` for YAML
#                                 validation, and all "top-level" schema functions.
# ├── utils.py                <-- An extensive set of marshmallow-related fields, methods, and schemas that are used
#                                 elsewhere in Ludwig.
# ├── trainer.py              <-- Contains `TrainerConfig()` and `get_trainer_jsonschema`
# ├── optimizers.py           <-- Contains every optimizer config (e.g. `SGDOptimizerConfig`, `AdamOptimizerConfig`,
#                                 etc.) and related marshmallow fields/methods.
# └── combiners/
#     ├── __init__.py         <-- Imports for each combiner config file (making imports elsewhere more convenient).
#     ├── utils.py            <-- Location of `combiner_registry`, `get_combiner_jsonschema()`, `get_combiner_conds()`
#     ├── base.py             <-- Location of `BaseCombinerConfig`
#     ├── comparator.py       <-- Location of `ComparatorCombinerConfig`
#     ... <file for each combiner> ...
#     └──  transformer.py     <-- Location of `TransformerCombinerConfig`
#

from functools import lru_cache
from threading import Lock
from typing import Any, Dict

from jsonschema import Draft7Validator, validate
from jsonschema.validators import extend

from ludwig.constants import (
    COMBINER,
    DEFAULTS,
    HYPEROPT,
    INPUT_FEATURES,
    MODEL_ECD,
    MODEL_TYPE,
    OUTPUT_FEATURES,
    PREPROCESSING,
    SPLIT,
    TRAINER,
)
from ludwig.schema.combiners.utils import get_combiner_jsonschema
from ludwig.schema.defaults.defaults import get_defaults_jsonschema
from ludwig.schema.features.utils import get_input_feature_jsonschema, get_output_feature_jsonschema
from ludwig.schema.hyperopt import get_hyperopt_jsonschema
from ludwig.schema.preprocessing import get_preprocessing_jsonschema
from ludwig.schema.trainer import get_model_type_jsonschema, get_trainer_jsonschema
from ludwig.schema.auxiliary_validations import (
    check_validation_metrics_are_valid,
    check_feature_names_unique,
    check_tied_features_are_valid,
    check_dependent_features,
    check_training_runway,
    check_gbm_horovod_incompatibility,
    check_gbm_feature_types,
    check_ray_backend_in_memory_preprocessing,
    check_sequence_concat_combiner_requirements,
    check_tabtransformer_combiner_requirements,
    check_comparator_combiner_requirements,
    check_class_balance_preprocessing,
    check_sampling_exclusivity,
    check_hyperopt_search_space,
    check_hyperopt_metric_targets,
    check_gbm_single_output_feature,
)

VALIDATION_LOCK = Lock()


@lru_cache(maxsize=2)
def get_schema(model_type: str = MODEL_ECD):
    schema = {
        "type": "object",
        "properties": {
            MODEL_TYPE: get_model_type_jsonschema(),
            INPUT_FEATURES: get_input_feature_jsonschema(),
            OUTPUT_FEATURES: get_output_feature_jsonschema(),
            COMBINER: get_combiner_jsonschema(),
            TRAINER: get_trainer_jsonschema(model_type),
            PREPROCESSING: get_preprocessing_jsonschema(),
            HYPEROPT: get_hyperopt_jsonschema(),
            DEFAULTS: get_defaults_jsonschema(),
        },
        "definitions": {},
        "required": [INPUT_FEATURES, OUTPUT_FEATURES],
    }
    return schema


@lru_cache(maxsize=2)
def get_validator():
    # Manually add support for tuples (pending upstream changes: https://github.com/Julian/jsonschema/issues/148):
    def custom_is_array(checker, instance):
        return isinstance(instance, list) or isinstance(instance, tuple)

    # This creates a new class, so cache to prevent a memory leak:
    # https://github.com/python-jsonschema/jsonschema/issues/868
    type_checker = Draft7Validator.TYPE_CHECKER.redefine("array", custom_is_array)
    return extend(Draft7Validator, type_checker=type_checker)


def validate_config(config: Dict[str, Any]):
    # Update config from previous versions to check that backwards compatibility will enable a valid config
    # NOTE: import here to prevent circular import
    from ludwig.data.split import get_splitter
    from ludwig.utils.backward_compatibility import upgrade_config_dict_to_latest_version

    # Update config from previous versions to check that backwards compatibility will enable a valid config
    updated_config = upgrade_config_dict_to_latest_version(config)
    model_type = updated_config.get(MODEL_TYPE, MODEL_ECD)

    splitter = get_splitter(**updated_config.get(PREPROCESSING, {}).get(SPLIT, {}))
    splitter.validate(updated_config)

    with VALIDATION_LOCK:
        # There is a race condition during schema validation that can cause the marshmallow schema class to
        # be missing during validation if more than one thread is trying to validate at once.
        validate(instance=updated_config, schema=get_schema(model_type=model_type), cls=get_validator())

    # Additional checks.
    check_validation_metrics_are_valid(updated_config)
    check_feature_names_unique(updated_config)
    check_tied_features_are_valid(updated_config)
    check_dependent_features(updated_config)
    check_training_runway(updated_config)
    check_gbm_horovod_incompatibility(updated_config)
    check_gbm_feature_types(updated_config)
    check_ray_backend_in_memory_preprocessing(updated_config)
    check_sequence_concat_combiner_requirements(updated_config)
    check_tabtransformer_combiner_requirements(updated_config)
    check_comparator_combiner_requirements(updated_config)
    check_class_balance_preprocessing(updated_config)
    check_sampling_exclusivity(updated_config)
    check_hyperopt_search_space(updated_config)
    check_hyperopt_metric_targets(updated_config)
    check_gbm_single_output_feature(updated_config)

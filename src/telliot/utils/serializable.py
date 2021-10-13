from typing import Any
from typing import ClassVar
from typing import Dict
from typing import Optional
from typing import Type

from pydantic import BaseModel


class SerializableModel(BaseModel):
    """A helper subclass that allows nested serialization

    The serialized format contains the class name, which can be used
    to reconstruct an object of the correct class.

    A registry is maintained to provide import context for
    reconstruction from the class name string.
    """

    #: Type Registry
    _registry_: ClassVar[Dict[str, Type[BaseModel]]] = dict()

    def __init_subclass__(cls, type: Optional[str] = None) -> None:
        """Register all subclasses"""
        cls._registry_[type or cls.__name__] = cls

    @classmethod
    def __get_validators__(cls) -> Any:
        yield cls._convert_to_model

    @classmethod
    def _convert_to_model(cls, data: Any) -> BaseModel:
        """Convert input to a class instance

        When input is a JSON string, it should have two attributes:

        - 'type': The class name
        - 'inputs': keyword arguments to pass to the constructor

        """

        if isinstance(data, BaseModel):
            return data

        data_type = data.get("type")

        if data_type is None:
            raise ValueError("Missing 'type'")

        factory = cls._registry_.get(data_type)

        if factory is None:
            raise TypeError(f"Unsupported type: {data_type}")

        inputs = data.get("inputs")

        if inputs is None:
            raise ValueError("Missing inputs")

        return factory(**inputs)

    @classmethod
    def parse_obj(cls, obj: Dict[str, Any]) -> Any:
        return cls._convert_to_model(obj)

    def dict(self, **d_args: Any) -> Dict[str, Any]:
        """Convert model to dict

        Override pydantic model to return a dict that includes
        the class name to help deserialization.
        """

        dr = {"type": self.__class__.__name__, "inputs": super().dict(**d_args)}

        return dr
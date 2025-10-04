from pydantic import BaseModel, field_validator, ValidationError
from pathlib import Path
from typing import List, Optional
import os

def validate_path_safe(path: str) -> str:
    """Validate that path does not contain traversal sequences."""
    if '..' in path:
        raise ValueError("Path contains directory traversal")
    return path

def validate_source_folder_path(path: str) -> str:
    """Validate that path does not contain traversal sequences. Absolute paths are permitted for source_folder."""
    if '..' in path:
        raise ValueError("Path contains directory traversal")
    return path

class PlaylistCreate(BaseModel):
    name: str
    files: List[str]
    source_folder: str

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @field_validator('files')
    @classmethod
    def files_not_empty(cls, v):
        if not v or len(v) == 0:
            raise ValueError("Files list cannot be empty")
        return v

    @field_validator('files', mode='before')
    @classmethod
    def validate_files(cls, v):
        if isinstance(v, list):
            for f in v:
                if not isinstance(f, str):
                    raise ValueError("All files must be strings")
                validate_path_safe(f)
        return v


class SaveTempPlaylist(BaseModel):
    temp_name: str
    new_name: str

    @field_validator('temp_name', 'new_name')
    @classmethod
    def names_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

class RemovePlaylist(BaseModel):
    name: str

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

class UpdatePlaylist(BaseModel):
    name: str
    source_folder: str
    temp_playlist: Optional[str] = None

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class RemoveFromPlaylist(BaseModel):
    name: str
    files: List[str]

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @field_validator('files')
    @classmethod
    def files_not_empty(cls, v):
        if not v or len(v) == 0:
            raise ValueError("Files list cannot be empty")
        return v

    @field_validator('files', mode='before')
    @classmethod
    def validate_files(cls, v):
        if isinstance(v, list):
            for f in v:
                if not isinstance(f, str):
                    raise ValueError("All files must be strings")
                validate_path_safe(f)
        return v
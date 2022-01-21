"""The Base class for all REDCap methods"""
from __future__ import annotations

import json

from typing import (
    Any,
    Dict,
    List,
    Optional,
    overload,
    Tuple,
    TYPE_CHECKING,
    Union,
)

from io import StringIO

from typing_extensions import Literal

from redcap.request import _ContentConfig, _RCRequest, RedcapError, FileUpload

if TYPE_CHECKING:
    import pandas as pd

# We're designing class to be lazy by default, and not hit the API unless
# explicitly requested by the user

# return_type type aliases
FileMap = Tuple[bytes, dict]
Json = List[Dict[str, Any]]
EmptyJson = List[dict]


class Base:
    """Base attributes and methods for the REDCap API"""

    def __init__(self, url: str, token: str, verify_ssl: Union[bool, str] = True):
        """Initialize a Project, validate url and token"""
        self._validate_url_and_token(url, token)
        self._url = url
        self._token = token
        self.verify_ssl = verify_ssl
        # attributes which require API calls
        self._metadata = None
        self._field_names = None
        self._def_field = None
        self._is_longitudinal = None

    @property
    def url(self) -> str:
        """API URL to a REDCap server"""
        return self._url

    @property
    def token(self) -> str:
        """API token to a project"""
        return self._token

    @property
    def metadata(self) -> List[Dict[str, Any]]:
        """Project metadata in JSON format"""
        if self._metadata is None:
            payload = self._initialize_payload("metadata", format_type="json")
            self._metadata = self._call_api(payload, return_type="json")

        return self._metadata

    @property
    def field_names(self) -> List[str]:
        """Project field names

        Note:
            These are survey field names, not export field names
        """
        if self._field_names is None:
            self._field_names = self._filter_metadata(key="field_name")

        return self._field_names

    @property
    def def_field(self) -> str:
        """The 'record_id' field equivalent for a project"""
        if self._def_field is None:
            self._def_field = self.field_names[0]

        return self._def_field

    @property
    def is_longitudinal(self) -> bool:
        """Whether or not this project is longitudinal"""
        if self._is_longitudinal is None:
            try:
                payload = self._initialize_payload(
                    content="formEventMapping", format_type="json"
                )
                self._call_api(payload, return_type="json")
                self._is_longitudinal = True
            except RedcapError:
                # we should only get a error back if there were no events defined
                # for the project
                self._is_longitudinal = False

        return self._is_longitudinal

    @staticmethod
    def _validate_url_and_token(url: str, token: str) -> None:
        """Run basic valiation on user supplied url and token"""
        url_actual_last_5 = url[-5:]
        url_expected_last_5 = "/api/"

        assert url_actual_last_5 == url_expected_last_5, (
            f"Incorrect url format '{ url }', url must end with",
            f"{ url_expected_last_5 }",
        )

        actual_token_len = len(token)
        expected_token_len = 32

        assert actual_token_len == expected_token_len, (
            f"Incorrect token format '{ token }', token must must be",
            f"{ expected_token_len } characters long",
        )

    # pylint: disable=import-outside-toplevel
    @staticmethod
    def _read_csv(buf: StringIO, **df_kwargs) -> "pd.DataFrame":
        """Wrapper around pandas read_csv that handles EmptyDataError"""
        import pandas as pd
        from pandas.errors import EmptyDataError

        try:
            dataframe = pd.read_csv(buf, **df_kwargs)
        except EmptyDataError:
            dataframe = pd.DataFrame()

        return dataframe

    # pylint: enable=import-outside-toplevel
    @overload
    def _filter_metadata(
        self,
        key: str,
        field_name: None = None,
    ) -> list:
        ...

    @overload
    def _filter_metadata(self, key: str, field_name: str) -> str:
        ...

    def _filter_metadata(self, key: str, field_name: Optional[str] = None):
        """Safely filter project metadata based off requested column and field_name"""
        if field_name:
            try:
                res = str(
                    [
                        row[key]
                        for row in self.metadata
                        if row["field_name"] == field_name
                    ][0]
                )
            except IndexError:  # pragma: no cover
                print(f"{ key } not in metadata field: { field_name }")
                return ""
        else:
            res = [row[key] for row in self.metadata]

        return res

    def _initialize_payload(
        self,
        content: str,
        format_type: Optional[Literal["json", "csv", "xml", "df"]] = None,
        return_format_type: Optional[Literal["json", "csv", "xml"]] = None,
        record_type: Literal["flat", "eav"] = "flat",
    ) -> Dict[str, str]:
        """Create the default dictionary for payloads

        This can be used as is for simple API requests or added to
        for more complex API requests.

        Args:
            content:
                The 'content' parameter documented in the REDCap API.
                e.g. 'record', 'metadata', 'file', 'event', etc.
            format_type: Format of the data returned for export methods
            return_format_type: Format of the data returned for import/delete methods
            record_type: The type of records being exported/imported
        """
        payload = {"token": self.token, "content": content}

        if format_type:
            if format_type == "df":
                payload["format"] = "csv"
            else:
                payload["format"] = format_type

        if return_format_type:
            payload["returnFormat"] = return_format_type

        if content == "record":
            payload["type"] = record_type

        return payload

    @overload
    def _initialize_import_payload(
        self,
        to_import: List[dict],
        import_format: Literal["json"],
        return_format_type: Literal["json", "csv", "xml"],
        data_type: Literal["record", "metadata"],
    ) -> Dict[str, Any]:
        ...

    @overload
    def _initialize_import_payload(
        self,
        to_import: str,
        import_format: Literal["csv", "xml"],
        return_format_type: Literal["json", "csv", "xml"],
        data_type: Literal["record", "metadata"],
    ) -> Dict[str, Any]:
        ...

    @overload
    def _initialize_import_payload(
        self,
        to_import: "pd.DataFrame",
        import_format: Literal["df"],
        return_format_type: Literal["json", "csv", "xml"],
        data_type: Literal["record", "metadata"],
    ) -> Dict[str, Any]:
        ...

    def _initialize_import_payload(
        self,
        to_import: Union[List[dict], str, "pd.DataFrame"],
        import_format: Literal["json", "csv", "xml", "df"],
        return_format_type: Literal["json", "csv", "xml"],
        data_type: Literal["record", "metadata"],
    ):
        """Standardize the data to be imported and add it to the payload

        Args:
            to_import: array of dicts, csv/xml string, ``pandas.DataFrame``
            import_format: Format of incoming data.
            data_type: The kind of data that are imported

        Returns:
            payload: The initialized payload dictionary and updated format
        """

        payload = self._initialize_payload(
            content=data_type, return_format_type=return_format_type
        )
        if import_format == "df":
            buf = StringIO()
            if data_type == "record":
                if self.is_longitudinal:
                    csv_kwargs = {"index_label": [self.def_field, "redcap_event_name"]}
                else:
                    csv_kwargs = {"index_label": self.def_field}
            elif data_type == "metadata":
                csv_kwargs = {"index": False}
            to_import.to_csv(buf, **csv_kwargs)
            payload["data"] = buf.getvalue()
            buf.close()
            import_format = "csv"
        elif import_format == "json":
            payload["data"] = json.dumps(to_import, separators=(",", ":"))
        else:
            # don't do anything to csv/xml
            payload["data"] = to_import

        payload["format"] = import_format
        return payload

    @staticmethod
    def _lookup_return_type(
        format_type: str,
        request_type: Literal["export", "import", "delete"] = "export",
        import_records_format: Optional[str] = None,
    ) -> str:
        """Look up a common return types based on format

        Non-standard return types will need to be passed directly
        to _call_api() via the return_type parameter.

        Args:
            format_type: The provided format for the API call
            request_type:
                The type of API request. Exports behave very differently
                from imports/deletes
            import_records_format:
                Format options from the import_records method. We
                need to use custom logic, because that method has
                different possible return types compared to all other
                methods
        """
        if format_type == "json":
            if request_type == "export":
                return_type = "json"
            elif request_type in ["import", "delete"] and not import_records_format:
                return_type = "int"
            elif import_records_format in ["count", "auto_ids"]:
                return_type = "count_dict"
            elif import_records_format == "ids":
                return_type = "ids_list"
            elif import_records_format == "nothing":
                return_type = "empty_json"
        elif format_type in ["csv", "xml", "df"]:
            return_type = "str"
        else:
            raise ValueError(f"Invalid format_type: { format_type }")

        return return_type

    @overload
    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal["file_map"],
        file: FileUpload,
    ) -> FileMap:
        ...

    @overload
    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal["json"],
        file: None = None,
    ) -> Json:
        ...

    @overload
    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal["empty_json"],
        file: None = None,
    ) -> EmptyJson:
        ...

    @overload
    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal["count_dict"],
        file: None = None,
    ) -> Dict[str, int]:
        ...

    @overload
    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal["ids_list"],
        file: None = None,
    ) -> List[str]:
        ...

    @overload
    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal["int"],
        file: None = None,
    ) -> int:
        ...

    @overload
    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal["str"],
        file: None = None,
    ) -> str:
        ...

    def _call_api(
        self,
        payload: Dict[str, Any],
        return_type: Literal[
            "file_map", "json", "empty_json", "count_dict", "ids_list", "str", "int"
        ],
        file: Optional[FileUpload] = None,
    ):
        """Make a POST Requst to the REDCap API

        Args:
            payload: Payload to send in POST request
            return_type:
                The data type of the return value. Used
                primarily for static typing, and developer
                understanding of the REDCap API
            file:
                File data to send with file-related API requests
        """
        config = _ContentConfig(
            return_empty_json=return_type == "empty_json",
            return_bytes=return_type == "file_map",
        )

        return_headers = return_type == "file_map"

        rcr = _RCRequest(url=self.url, payload=payload, config=config)
        return rcr.execute(
            verify_ssl=self.verify_ssl, return_headers=return_headers, file=file
        )
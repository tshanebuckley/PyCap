"""REDCap API methods for Project files"""

from typing import TYPE_CHECKING, Optional, Union

from redcap.methods.base import Base, EmptyJson, FileMap

if TYPE_CHECKING:
    from io import TextIOWrapper


class Files(Base):
    """Responsible for all API methods under 'Files' in the API Playground"""

    def _check_file_field(self, field: str) -> None:
        """Check that field exists and is a file field"""
        # Since we initialize self.field_names as None, pylint worries that this will
        # produce an error
        # pylint: disable=unsupported-membership-test
        is_field = field in self.field_names
        # pylint: enable=unsupported-membership-test
        is_file = self._filter_metadata(key="field_type", field_name=field) == "file"
        if not (is_field and is_file):
            msg = f"'{ field }' is not a field or not a 'file' field"
            raise ValueError(msg)

    def export_file(
        self,
        record: str,
        field: str,
        event: Optional[str] = None,
        repeat_instance: Optional[int] = None,
        return_coroutine: bool = False,
    ) -> FileMap:
        """
        Export the contents of a file stored for a particular record

        Note:
            Unlike other export methods, this only works on a single record.

        Args:
            record: Record ID
            field: Field name containing the file to be exported.
            event: For longitudinal projects, the unique event name
            repeat_instance:
                (Only for projects with repeating instruments/events)
                The repeat instance number of the repeating event (if longitudinal)
                or the repeating instrument (if classic or longitudinal).

        Returns:
            Content of the file and content-type dictionary

        Raises:
            ValueError: Incorrect file field
            RedcapError: Bad Request e.g. invalid record_id

        Examples:
            If your project has events, then you must specifiy the event of interest.
            Otherwise, you can leave the event parameter blank

            >>> proj.export_file(record="1", field="upload_field", event="event_1_arm_1")
            (b'test upload\\n', {'name': 'test_upload.txt', 'charset': 'UTF-8'})
        """
        self._check_file_field(field)
        # load up payload
        def _build_payload(**kwargs):
            payload = self._initialize_payload(content="file")
            # there's no format field in this call
            payload["action"] = "export"
            payload["field"] = field
            payload["record"] = record
            if event:
                payload["event"] = event
            if repeat_instance:
                payload["repeat_instance"] = str(repeat_instance)
            return payload
        # This might just be due to some typing issues, maybe we can come back and
        # remove this disable eventually.
        # pylint: disable=unpacking-non-sequence
        content, headers = self._call_api(
            payload=_build_payload,
            return_type="file_map",
            return_coroutine=return_coroutine,
            kwargs=locals(),
        )
        # pylint: enable=unpacking-non-sequence
        # REDCap adds some useful things in content-type
        content_map = {}
        if "content-type" in headers:
            splat = [
                key_values.strip() for key_values in headers["content-type"].split(";")
            ]
            key_values = [
                (key_values.split("=")[0], key_values.split("=")[1].replace('"', ""))
                for key_values in splat
                if "=" in key_values
            ]
            content_map = dict(key_values)

        return content, content_map

    def import_file(
        self,
        record: str,
        field: str,
        file_name: str,
        file_object: "TextIOWrapper",
        event: Optional[str] = None,
        repeat_instance: Optional[Union[int, str]] = None,
        return_coroutine: bool = False,
    ) -> EmptyJson:
        """
        Import the contents of a file represented by file_object to a
        particular records field

        Args:
            record: Record ID
            field: Field name where the file will go
            file_name: File name visible in REDCap UI
            file_object: File object as returned by `open`
            event: For longitudinal projects, the unique event name
            repeat_instance:
                (Only for projects with repeating instruments/events)
                The repeat instance number of the repeating event (if longitudinal)
                or the repeating instrument (if classic or longitudinal).

        Returns:
            Empty JSON object

        Raises:
            ValueError: Incorrect file field
            RedcapError: Bad Request e.g. invalid record_id

        Examples:
            If your project has events, then you must specifiy the event of interest.
            Otherwise, you can leave the event parameter blank

            >>> import tempfile
            >>> tmp_file = tempfile.TemporaryFile()
            >>> proj.import_file(
            ...     record="2",
            ...     field="upload_field",
            ...     file_name="myupload.txt",
            ...     file_object=tmp_file,
            ...     event="event_1_arm_1",
            ... )
            [{}]
        """
        self._check_file_field(field)
        # load up payload
        def _build_payload(**kwargs):
            payload = self._initialize_payload(content="file")
            payload["action"] = "import"
            payload["field"] = kwargs["field"]
            payload["record"] = kwargs["record"]
            if event:
                payload["event"] = kwargs["event"]
            if repeat_instance:
                payload["repeat_instance"] = kwargs["repeat_instance"]
            return payload

        file_upload_dict = {"file": (file_name, file_object)}

        return self._call_api(
            payload=_build_payload,
            return_type="empty_json",
            file=file_upload_dict,
            return_coroutine=return_coroutine,
            kwargs=locals()
        )

    def delete_file(
        self,
        record: str,
        field: str,
        event: Optional[str] = None,
        return_coroutine: bool = False,
    ) -> EmptyJson:
        """
        Delete a file from REDCap

        Note:
            There is no undo button to this.

        Args:
            record: Record ID
            field: Field name
            event: For longitudinal projects, the unique event name

        Returns:
            Empty JSON object

        Raises:
            ValueError: Incorrect file field
            RedcapError: Bad Request e.g. invalid record_id

        Examples:
            Import a tempfile and then delete it

            >>> import tempfile
            >>> tmp_file = tempfile.TemporaryFile()
            >>> proj.import_file(
            ...     record="2",
            ...     field="upload_field",
            ...     file_name="myupload.txt",
            ...     file_object=tmp_file,
            ...     event="event_1_arm_1",
            ... )
            [{}]
            >>> proj.delete_file(record="2", field="upload_field", event="event_1_arm_1")
            [{}]
        """
        self._check_file_field(field)
        # Load up payload
        def _build_payload(**kwargs):
            payload = self._initialize_payload(content="file")
            payload["action"] = "delete"
            payload["record"] = record
            payload["field"] = field
            if event:
                payload["event"] = event
            return payload

        return self._call_api(
            payload=_build_payload,
            return_type="empty_json",
            return_coroutine=return_coroutine,
            kwargs=locals()
        )

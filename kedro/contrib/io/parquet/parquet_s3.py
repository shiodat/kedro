# Copyright 2018-2019 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
#     or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""``ParquetS3DataSet`` is a data set used to load and save
data to parquet files on S3
"""
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Dict

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from s3fs.core import S3FileSystem

from kedro.io.core import AbstractVersionedDataSet, Version


class ParquetS3DataSet(AbstractVersionedDataSet):
    """``ParquetS3DataSet`` loads and saves data to a file in S3. It uses s3fs
        to read and write from S3 and pandas to handle the parquet file.

        Example:
        ::

            >>> from kedro.contrib.io.parquet.parquet_s3 import ParquetS3DataSet
            >>> import pandas as pd
            >>>
            >>> data = pd.DataFrame({'col1': [1, 2], 'col2': [4, 5],
            >>>                      'col3': [5, 6]})
            >>>
            >>> data_set = ParquetS3DataSet(
            >>>                         filepath="temp3.parquet",
            >>>                         bucket_name="test_bucket",
            >>>                         credentials={
            >>>                             'aws_access_key_id': 'YOUR_KEY',
            >>>                             'aws_access_secredt_key': 'YOUR SECRET'},
            >>>                         save_args={"compression": "GZIP"})
            >>> data_set.save(data)
            >>> reloaded = data_set.load()
            >>>
            >>> assert data.equals(reloaded)
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        filepath: str,
        bucket_name: str = None,
        credentials: Dict[str, Any] = None,
        load_args: Dict[str, Any] = None,
        save_args: Dict[str, Any] = None,
        version: Version = None,
    ) -> None:
        """Creates a new instance of ``ParquetS3DataSet`` pointing to a concrete
        parquet file on S3.

        Args:
            filepath: Path to a parquet file, parquet collection or the directory
                of a multipart parquet. May contain the full path in S3 including
                bucket and protocol, e.g. `s3://bucket-name/path/to/file.parquet`.
            bucket_name: S3 bucket name. Must be specified **only** if not
                present in ``filepath``.
            credentials: Credentials to access the S3 bucket, such as
                ``aws_access_key_id``, ``aws_secret_access_key``.
            load_args: Additional loading options `pyarrow`:
                https://arrow.apache.org/docs/python/generated/pyarrow.parquet.read_table.html
                or `fastparquet`:
                https://fastparquet.readthedocs.io/en/latest/api.html#fastparquet.ParquetFile.to_pandas
            save_args: Additional saving options for `pyarrow`:
                https://arrow.apache.org/docs/python/generated/pyarrow.Table.html#pyarrow.Table.from_pandas
                or `fastparquet`:
                https://fastparquet.readthedocs.io/en/latest/api.html#fastparquet.write
            version: If specified, should be an instance of
                ``kedro.io.core.Version``. If its ``load`` attribute is
                None, the latest version will be loaded. If its ``save``
                attribute is None, save version will be autogenerated.
        """

        _credentials = deepcopy(credentials) or {}
        _s3 = S3FileSystem(client_kwargs=_credentials)
        path = _s3._strip_protocol(filepath)  # pylint: disable=protected-access
        path = PurePosixPath("{}/{}".format(bucket_name, path) if bucket_name else path)
        super().__init__(
            path, version, exists_function=_s3.exists, glob_function=_s3.glob,
        )

        default_load_args = {}  # type: Dict[str, Any]
        default_save_args = {}  # type: Dict[str, Any]

        self._load_args = (
            {**default_load_args, **load_args}
            if load_args is not None
            else default_load_args
        )
        self._save_args = (
            {**default_save_args, **save_args}
            if save_args is not None
            else default_save_args
        )

        self._credentials = _credentials
        self._s3 = _s3

    def _describe(self) -> Dict[str, Any]:
        return dict(
            filepath=self._filepath,
            load_args=self._load_args,
            save_args=self._save_args,
            version=self._version,
        )

    def _load(self) -> pd.DataFrame:
        load_path = PurePosixPath(self._get_load_path())

        with self._s3.open(str(load_path), mode="rb") as s3_file:
            return pd.read_parquet(s3_file, **self._load_args)

    def _save(self, data: pd.DataFrame) -> None:
        save_path = str(self._get_save_path())

        pq.write_table(
            table=pa.Table.from_pandas(data),
            where=save_path,
            filesystem=self._s3,
            **self._save_args,
        )

    def _exists(self) -> bool:
        load_path = self._get_load_path()
        return self._s3.isfile(str(PurePosixPath(load_path)))

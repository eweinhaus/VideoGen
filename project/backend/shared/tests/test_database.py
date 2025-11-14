"""
Tests for database client.
"""

import pytest
import sys
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Mock supabase and its submodules before importing shared modules
mock_supabase = Mock()
mock_supabase.lib = Mock()
mock_supabase.lib.client_options = Mock()
mock_supabase.lib.client_options.ClientOptions = Mock
sys.modules['supabase'] = mock_supabase
sys.modules['supabase.lib'] = mock_supabase.lib
sys.modules['supabase.lib.client_options'] = mock_supabase.lib.client_options

from shared.database import DatabaseClient, AsyncTableQueryBuilder
from shared.errors import RetryableError, ConfigError


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    client = Mock()
    client.table = Mock(return_value=Mock())
    return client


@pytest.fixture
def db_client(mock_supabase_client):
    """Create a database client with mocked Supabase."""
    with patch("shared.database.create_client", return_value=mock_supabase_client):
        with patch("shared.database.settings") as mock_settings:
            mock_settings.supabase_url = "https://test.supabase.co"
            mock_settings.supabase_service_key = "test_key"
            client = DatabaseClient()
            client.client = mock_supabase_client
            return client


@pytest.mark.asyncio
async def test_database_client_initialization():
    """Test that database client initializes correctly."""
    with patch("shared.database.create_client") as mock_create:
        mock_client = Mock()
        mock_create.return_value = mock_client
        
        with patch("shared.database.settings") as mock_settings:
            mock_settings.supabase_url = "https://test.supabase.co"
            mock_settings.supabase_service_key = "test_key"
            
            client = DatabaseClient()
            assert client.client == mock_client
            mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_database_client_initialization_failure():
    """Test that ConfigError is raised on initialization failure."""
    with patch("shared.database.create_client", side_effect=Exception("Connection failed")):
        with patch("shared.database.settings") as mock_settings:
            mock_settings.supabase_url = "https://test.supabase.co"
            mock_settings.supabase_service_key = "test_key"
            
            with pytest.raises(ConfigError, match="Failed to initialize database client"):
                DatabaseClient()


@pytest.mark.asyncio
async def test_table_query_builder(db_client):
    """Test that table query builder works correctly."""
    # Create a chainable mock query builder
    mock_query_result = Mock()
    mock_query_result.data = [{"id": "123"}]
    
    mock_query = Mock()
    mock_query.execute = Mock(return_value=mock_query_result)
    mock_query.eq = Mock(return_value=mock_query)
    mock_query.limit = Mock(return_value=mock_query)
    
    mock_table = Mock()
    mock_table.select = Mock(return_value=mock_query)
    
    db_client.client.table = Mock(return_value=mock_table)
    
    # Test select
    builder = db_client.table("jobs")
    builder.select("*")
    builder.eq("id", "123")
    builder.limit(1)
    result = await builder.execute()
    
    assert result.data == [{"id": "123"}]
    mock_table.select.assert_called_once_with("*")
    mock_query.eq.assert_called_once_with("id", "123")
    mock_query.limit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_database_health_check_success(db_client):
    """Test that health check returns True on success."""
    mock_table = Mock()
    mock_query = Mock()
    mock_table.select = Mock(return_value=mock_query)
    mock_query.limit = Mock(return_value=mock_query)
    mock_query.execute = Mock(return_value=Mock(data=[{"id": "123"}]))
    
    db_client.client.table = Mock(return_value=mock_table)
    
    is_healthy = await db_client.health_check()
    assert is_healthy is True


@pytest.mark.asyncio
async def test_database_health_check_failure(db_client):
    """Test that health check returns False on failure."""
    mock_table = Mock()
    mock_query = Mock()
    mock_table.select = Mock(return_value=mock_query)
    mock_query.limit = Mock(return_value=mock_query)
    mock_query.execute = Mock(side_effect=Exception("Connection failed"))
    
    db_client.client.table = Mock(return_value=mock_table)
    
    is_healthy = await db_client.health_check()
    assert is_healthy is False


@pytest.mark.asyncio
async def test_database_retry_on_failure(db_client):
    """Test that database retries on failure."""
    call_count = 0
    
    def mock_execute():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Temporary failure")
        return Mock(data=[{"id": "123"}])
    
    mock_table = Mock()
    mock_query = Mock()
    mock_table.select = Mock(return_value=mock_query)
    mock_query.limit = Mock(return_value=mock_query)
    mock_query.execute = Mock(side_effect=mock_execute)
    
    db_client.client.table = Mock(return_value=mock_table)
    
    builder = db_client.table("jobs")
    result = await builder.select("*").limit(1).execute()
    
    assert result.data == [{"id": "123"}]
    assert call_count == 3  # Should retry 3 times


@pytest.mark.asyncio
async def test_database_raises_retryable_error_after_max_attempts(db_client):
    """Test that RetryableError is raised after max attempts."""
    mock_table = Mock()
    mock_query = Mock()
    mock_table.select = Mock(return_value=mock_query)
    mock_query.limit = Mock(return_value=mock_query)
    mock_query.execute = Mock(side_effect=Exception("Always fails"))
    
    db_client.client.table = Mock(return_value=mock_table)
    
    builder = db_client.table("jobs")
    
    with pytest.raises(RetryableError, match="Database operation failed"):
        await builder.select("*").limit(1).execute()


@pytest.mark.asyncio
async def test_database_transaction_context_manager(db_client):
    """Test that transaction context manager works (placeholder)."""
    with db_client.transaction() as client:
        assert client == db_client.client
    
    # Transaction is a placeholder, so it just returns the client
    # No actual transaction behavior


@pytest.mark.asyncio
async def test_database_close(db_client):
    """Test that close method works (no-op for Supabase)."""
    # Should not raise
    await db_client.close()


@pytest.mark.asyncio
async def test_async_table_query_builder_chaining(db_client):
    """Test that query builder methods can be chained."""
    mock_table = Mock()
    mock_query = Mock()
    
    # Setup chain
    mock_table.insert = Mock(return_value=mock_query)
    mock_query.execute = Mock(return_value=Mock(data=[{"id": "123"}]))
    
    db_client.client.table = Mock(return_value=mock_table)
    
    builder = db_client.table("jobs")
    result = await builder.insert({"id": "123"}).execute()
    
    assert result.data == [{"id": "123"}]
    mock_table.insert.assert_called_once_with({"id": "123"})


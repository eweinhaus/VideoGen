"""
Playwright browser tests for Audio Parser via frontend.

These tests require:
- Frontend running on localhost:3000
- API Gateway running on localhost:8000
- Worker process running
"""
import pytest

try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@pytest.fixture(scope="module")
async def browser():
    """Create browser instance for tests."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed. Install with: pip install playwright && playwright install chromium")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest.fixture
async def page(browser):
    """Create a new page for each test."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    
    page = await browser.new_page()
    yield page
    await page.close()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_upload_via_frontend(page: Page):
    """
    Test audio upload and processing via frontend UI.
    
    Note: Requires frontend and backend services running.
    """
    pytest.skip("Requires frontend and backend services running")
    
    # Navigate to upload page
    await page.goto("http://localhost:3000/upload")
    
    # Wait for page to load
    await page.wait_for_selector("input[type='file']", timeout=5000)
    
    # Upload audio file
    # Note: Requires actual audio file
    audio_file_path = "tests/fixtures/test_audio.mp3"
    try:
        file_input = page.locator("input[type='file']")
        await file_input.set_input_files(audio_file_path)
    except FileNotFoundError:
        pytest.skip(f"Test audio file not found: {audio_file_path}")
    
    # Fill in prompt
    prompt_input = page.locator("textarea[name='prompt'], textarea[placeholder*='prompt']")
    await prompt_input.fill("Create a cyberpunk music video")
    
    # Submit form
    submit_button = page.locator("button[type='submit'], button:has-text('Submit'), button:has-text('Upload')")
    await submit_button.click()
    
    # Wait for redirect to job page
    await page.wait_for_url("**/jobs/*", timeout=10000)
    
    # Verify job page loaded
    job_id = page.url.split("/jobs/")[-1]
    assert job_id
    
    # Wait for processing to start
    await page.wait_for_selector("text=Processing, text=processing", timeout=10000)
    
    # Monitor progress updates
    # Look for progress indicators
    progress_indicator = page.locator("[data-testid='progress'], .progress, [role='progressbar']")
    await progress_indicator.wait_for(state="visible", timeout=5000)
    
    # Wait for completion (with timeout)
    max_wait = 120000  # 2 minutes
    start_time = await page.evaluate("Date.now()")
    
    while True:
        status_text = await page.locator("[data-testid='status'], .status").text_content()
        
        if status_text and ("completed" in status_text.lower() or "done" in status_text.lower()):
            break
        elif status_text and "failed" in status_text.lower():
            pytest.fail("Job failed")
        
        elapsed = await page.evaluate("Date.now()") - start_time
        if elapsed > max_wait:
            pytest.fail("Processing timeout")
        
        await page.wait_for_timeout(2000)  # Wait 2 seconds
    
    # Verify results displayed
    # Look for BPM, beats, structure, etc.
    bpm_display = page.locator("[data-testid='bpm'], text=/BPM/i")
    if await bpm_display.count() > 0:
        assert await bpm_display.first.is_visible()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_parser_progress_tracking(page: Page):
    """
    Test real-time progress updates via SSE.
    
    Note: Requires frontend and backend services running.
    """
    pytest.skip("Requires frontend and backend services running")
    
    # Navigate to job page (use actual job ID from previous test or create new)
    job_id = "test-job-id"  # Replace with actual job ID
    await page.goto(f"http://localhost:3000/jobs/{job_id}")
    
    # Monitor SSE events
    # Check for progress updates in UI
    progress_bar = page.locator("[data-testid='progress-bar'], [role='progressbar']")
    
    if await progress_bar.count() > 0:
        # Wait for progress to update
        initial_progress = await progress_bar.first.get_attribute("value") or "0"
        
        # Wait for progress to increase
        await page.wait_for_function(
            """
            () => {
                const progressBar = document.querySelector('[data-testid="progress-bar"], [role="progressbar"]');
                return progressBar && parseFloat(progressBar.value || progressBar.getAttribute('aria-valuenow') || 0) > 0;
            }
            """,
            timeout=30000
        )
        
        # Verify progress increased
        final_progress = await progress_bar.first.get_attribute("value") or await progress_bar.first.get_attribute("aria-valuenow") or "0"
        assert float(final_progress) > float(initial_progress)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_parser_error_display(page: Page):
    """
    Test error display for invalid audio files.
    
    Note: Requires frontend and backend services running.
    """
    pytest.skip("Requires frontend and backend services running")
    
    # Navigate to upload page
    await page.goto("http://localhost:3000/upload")
    
    # Upload invalid file (e.g., .txt file)
    file_input = page.locator("input[type='file']")
    await file_input.set_input_files("tests/fixtures/invalid_file.txt")
    
    # Verify error message displayed
    error_message = page.locator("[data-testid='error'], .error, [role='alert']")
    await error_message.wait_for(state="visible", timeout=5000)
    
    error_text = await error_message.text_content()
    assert error_text and ("invalid" in error_text.lower() or "error" in error_text.lower())


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audio_parser_results_display(page: Page):
    """
    Test that audio analysis results are displayed correctly.
    
    Note: Requires frontend and backend services running.
    """
    pytest.skip("Requires frontend and backend services running")
    
    # Navigate to completed job page
    job_id = "completed-job-id"  # Replace with actual completed job ID
    await page.goto(f"http://localhost:3000/jobs/{job_id}")
    
    # Verify results are displayed
    # Look for BPM, beats count, structure segments, mood, etc.
    results_section = page.locator("[data-testid='audio-results'], .audio-results")
    
    if await results_section.count() > 0:
        assert await results_section.first.is_visible()
        
        # Check for key metrics
        bpm_text = page.locator("text=/BPM/i, text=/bpm/i")
        if await bpm_text.count() > 0:
            assert await bpm_text.first.is_visible()


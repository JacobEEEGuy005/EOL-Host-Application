# CAN Decoding Bottleneck Analysis

## Issue
CAN signals are being skipped/not updated, indicating a bottleneck in the decoding pipeline.

## Current Architecture

### Frame Reception Flow
1. **AdapterWorker Thread** (background)
   - Continuously receives frames via `adapter.iter_recv()`
   - Enqueues ALL frames into `frame_queue` (unbounded `queue.Queue()`)
   - No rate limiting or dropping

2. **Polling Timer** (`_poll_frames`)
   - Called every **150ms** (`FRAME_POLL_INTERVAL_MS`)
   - Processes frames from `frame_queue`
   - Runs in main UI thread

3. **Frame Processing** (`_add_frame_row`)
   - Adds frame to frame table (UI update)
   - Appends to message log (UI update)
   - Calls `_decode_and_add_signals()` (expensive)

4. **Signal Decoding** (`_decode_and_add_signals`)
   - Calls `SignalService.decode_frame()` (DBC lookup + decode)
   - Updates signal table (multiple UI updates per frame)
   - Updates feedback label
   - All synchronous in main thread

## Identified Bottlenecks

### 1. **CRITICAL BUG: Only Last Frame Processed Per Poll** ⚠️
**Location**: `_poll_frames()` lines 3837-3839

```python
while not self.can_service.frame_queue.empty():
    f = self.can_service.frame_queue.get_nowait()
self._add_frame_row(f)  # ❌ OUTSIDE THE LOOP!
```

**Problem**: The `while` loop dequeues all frames from the queue, but only the **last frame** is processed. All other frames are **lost/discarded**.

**Impact**: 
- If 100 frames arrive between polls, only the 100th frame is decoded
- 99 frames are silently discarded
- Signal updates are completely skipped for discarded frames

**Fix**: Move `_add_frame_row(f)` inside the loop.

### 2. **Slow Polling Interval**
- **Current**: 150ms (~6.67 polls/second)
- **Problem**: If frames arrive at >6.67 Hz, they accumulate in the queue
- **Impact**: Queue grows unbounded, causing memory issues and processing delays

### 3. **Unbounded Queue**
- **Current**: `queue.Queue()` with no `maxsize`
- **Problem**: Queue can grow indefinitely, consuming memory
- **Impact**: System slowdown, delayed processing

### 4. **Expensive Synchronous UI Updates**
- Each frame triggers:
  - Table row insertion (expensive)
  - Message log update (expensive)
  - Signal table updates (multiple setItem calls)
  - Feedback label updates
- All in main UI thread, blocking processing
- **Impact**: If processing 100 frames takes >150ms, next poll is delayed

### 5. **No Frame Rate Limiting**
- Processing all frames in queue without limit
- If queue has 1000 frames, all processed in one poll
- **Impact**: UI freezes, signals skipped

### 6. **Signal Cache Overwrites**
- SignalService caches only latest value per signal
- If multiple frames arrive for same signal, only last one cached
- **Impact**: Intermediate values are lost (though this might be intentional)

## Performance Analysis

**Scenario**: CAN bus sending at 100 Hz (10ms between frames)

- **Poll rate**: 150ms = ~6.67 polls/sec
- **Frames per poll**: 100 Hz / 6.67 polls = **~15 frames** accumulate per poll
- **Processing time per frame**: ~5-10ms (decode + UI updates)
- **Total time for 15 frames**: 75-150ms

**Result**: 
- Queue grows: 15 frames accumulate every 150ms
- Processing takes 75-150ms (within poll interval, but growing)
- Eventually queue grows too large and processing can't keep up

**With the bug**: Only 1 frame per poll is processed (last one), so queue grows even faster!

## Recommended Fixes

### Priority 1: Fix Critical Bug
```python
def _poll_frames(self):
    try:
        if self.can_service is not None:
            frames_processed = 0
            max_frames_per_poll = 50  # Limit frames per poll
            
            while not self.can_service.frame_queue.empty() and frames_processed < max_frames_per_poll:
                f = self.can_service.frame_queue.get_nowait()
                self._add_frame_row(f)  # ✅ INSIDE THE LOOP
                frames_processed += 1
            
            if frames_processed > 0:
                logger.debug(f"Processed {frames_processed} frames in this poll")
    except Exception as e:
        logger.error(f"Error polling frames: {e}", exc_info=True)
```

### Priority 2: Reduce Polling Interval
- `FRAME_POLL_INTERVAL_MS` is already **10ms** (previously reduced from 150ms)
- Provides ~100 polls/second
- Good match for high-rate CAN traffic

### Priority 3: Add Frame Rate Limiting
- Limit frames processed per poll (e.g., 50 frames max)
- Prevents UI freeze from large queues
- Remaining frames processed in next poll

### Priority 4: Optimize UI Updates
- Batch UI updates
- Use `setUpdatesEnabled(False)` during bulk updates
- Defer non-critical updates (logging, scrolling)

### Priority 5: Add Queue Size Monitoring
- Monitor queue size and warn if too large
- Optionally drop oldest frames if queue exceeds limit

## Expected Improvements

After fixes:
- **No frames lost**: All frames processed (bug fix)
- **Faster updates**: 10ms polling = ~100 polls/sec (already optimized)
- **Better responsiveness**: Frame rate limiting prevents UI freeze
- **Bounded memory**: Queue monitoring prevents unbounded growth

## Status
✅ **CRITICAL BUG FIXED**: `_add_frame_row()` now called inside the loop
✅ **Frame rate limiting added**: MAX_FRAMES_PER_POLL = 100
✅ **Polling interval**: Already optimized to 10ms
✅ **Queue monitoring**: Added logging for diagnostics


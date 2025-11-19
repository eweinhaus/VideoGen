"""
Song structure classification.

Analyze song structure (intro/verse/chorus/bridge/outro) using chroma features and clustering.
"""

import numpy as np
from typing import List, Tuple

import librosa
from sklearn.cluster import AgglomerativeClustering

from shared.models.audio import SongStructure, ClipBoundary
from shared.logging import get_logger

logger = get_logger("audio_parser")


def _calculate_segment_energy(y_segment: np.ndarray, sr: int, max_rms: float = None, max_centroid: float = None) -> float:
    """
    Calculate energy level for segment classification (low/medium/high).
    
    Args:
        y_segment: Audio segment signal
        sr: Sample rate
        max_rms: Maximum RMS from full track (for normalization)
        max_centroid: Maximum spectral centroid from full track (for normalization)
        
    Returns:
        Energy value (0.0-1.0)
    """
    # Compute RMS
    rms = librosa.feature.rms(y=y_segment)[0]
    rms_mean = np.mean(rms)
    
    # Compute spectral centroid
    centroid = librosa.feature.spectral_centroid(y=y_segment, sr=sr)[0]
    centroid_mean = np.mean(centroid)
    
    # Normalize RMS
    max_rms = max_rms or 1.0
    rms_norm = min(rms_mean / max_rms, 1.0) if max_rms > 0 else 0.0
    
    # Normalize centroid
    max_centroid = max_centroid or 5000.0
    centroid_norm = min(centroid_mean / max_centroid, 1.0) if max_centroid > 0 else 0.0
    
    # Combine: weighted average
    energy = (rms_norm * 0.6) + (centroid_norm * 0.4)
    
    # Clamp to [0.0, 1.0]
    energy = max(0.0, min(1.0, energy))
    
    return float(energy)


def calculate_segment_beat_intensity(
    segment: SongStructure,
    beat_timestamps: List[float],
    audio: np.ndarray,
    sr: int
) -> str:
    """
    Calculate beat intensity (high/medium/low) for a segment.
    
    Uses beat density (beats per second) + energy level.
    
    Args:
        segment: SongStructure segment
        beat_timestamps: All beat timestamps
        audio: Full audio signal
        sr: Sample rate
        
    Returns:
        'high', 'medium', or 'low'
    """
    # Find beats within segment
    beats_in_segment = [
        b for b in beat_timestamps 
        if segment.start <= b <= segment.end
    ]
    
    if not beats_in_segment:
        return "low"
    
    # Calculate beat density
    segment_duration = segment.end - segment.start
    if segment_duration <= 0:
        return "low"
    
    beats_per_second = len(beats_in_segment) / segment_duration
    bpm_equivalent = beats_per_second * 60
    
    # Calculate energy for segment
    start_frame = int(segment.start * sr)
    end_frame = int(segment.end * sr)
    if end_frame > len(audio):
        end_frame = len(audio)
    if start_frame >= end_frame:
        return "low"
    
    segment_audio = audio[start_frame:end_frame]
    energy = _calculate_segment_energy(segment_audio, sr)
    
    # Classification rules
    if bpm_equivalent > 120 and energy > 0.7:
        return "high"
    elif bpm_equivalent < 90 and energy < 0.4:
        return "low"
    elif bpm_equivalent > 120 or energy > 0.7:
        return "high"  # Either condition met
    elif bpm_equivalent < 90 or energy < 0.4:
        return "low"  # Either condition met
    else:
        return "medium"


def _labels_to_segments(
    labels: np.ndarray,
    sr: int,
    duration: float,
    hop_length: int = 512,
    min_segment_duration: float = 7.0
) -> List[Tuple[float, float, int]]:
    """
    Convert frame-level labels into contiguous time segments.

    Uses a smarter approach: finds cluster boundaries by identifying
    where labels change, then uses median positions of each cluster
    to determine segment boundaries.

    Note: min_segment_duration (default 7.0s) is for structure segments.
    Structure segments will be subdivided into multiple 5-8s clips by the boundaries generator.
    """
    logger.info(f"🔍 DETAILED: _labels_to_segments called: n_frames={len(labels)}, duration={duration:.2f}s, min_segment_duration={min_segment_duration}s")
    
    labels_array = np.asarray(labels, dtype=int)
    n_frames = len(labels_array)
    if n_frames == 0 or duration <= 0:
        logger.warning(f"🔍 DETAILED: Empty labels or duration, returning single segment")
        return [(0.0, max(duration, 0.1), 0)]
    
    min_frame_gap = max(1, int(round((min_segment_duration * sr) / hop_length)))
    logger.info(f"🔍 DETAILED: min_frame_gap={min_frame_gap} frames (min_segment_duration={min_segment_duration}s)")
    
    # Find unique labels
    unique_labels = np.unique(labels_array)
    logger.info(f"🔍 DETAILED: Unique labels: {unique_labels}, count: {len(unique_labels)}")
    
    # CRITICAL: AgglomerativeClustering doesn't guarantee contiguous labels!
    # Labels might be scattered: [0,1,2,0,1,2,0,1,2...]
    # We need to find CONTIGUOUS regions where labels are the same
    
    # Find all label transitions (where label changes)
    label_changes = []
    for idx in range(1, n_frames):
        if labels_array[idx] != labels_array[idx - 1]:
            label_changes.append((idx, labels_array[idx - 1], labels_array[idx]))
    
    logger.info(f"🔍 DETAILED: Found {len(label_changes)} label transitions")
    if len(label_changes) > 0:
        logger.info(f"🔍 DETAILED: First 10 transitions: {label_changes[:10]}")
        logger.info(f"🔍 DETAILED: Last 10 transitions: {label_changes[-10:]}")
        # Check if transitions are all at the end
        if len(label_changes) > 0:
            first_transition_frame = label_changes[0][0]
            last_transition_frame = label_changes[-1][0]
            logger.info(f"🔍 DETAILED: Transitions span frames {first_transition_frame} to {last_transition_frame} (out of {n_frames})")
            if last_transition_frame > n_frames * 0.95:
                logger.warning(f"🔍 DETAILED: ⚠️ Most transitions are at the END of audio (>95%)!")
    
    # Build frame boundaries from label transitions
    # Only include transitions that are far enough apart (min_segment_duration)
    frame_boundaries = [0]
    
    for change_idx, (frame_idx, old_label, new_label) in enumerate(label_changes):
        # Check if this boundary is far enough from the last one
        if frame_idx - frame_boundaries[-1] >= min_frame_gap:
            frame_boundaries.append(frame_idx)
            logger.debug(f"🔍 DETAILED: Added boundary at frame {frame_idx} (transition {change_idx+1}/{len(label_changes)})")
        else:
            logger.debug(f"🔍 DETAILED: Skipped boundary at frame {frame_idx} (too close: {frame_idx - frame_boundaries[-1]} < {min_frame_gap})")
    
    # Always add the final boundary
    if frame_boundaries[-1] != n_frames:
        frame_boundaries.append(n_frames)
    
    logger.info(f"🔍 DETAILED: frame_boundaries after filtering: {frame_boundaries[:15]}... (total: {len(frame_boundaries)})")
    
    # If we still only have 2 boundaries, the problem is that all label changes
    # are clustered together (likely at the end). This suggests:
    # 1. Clustering assigned most frames the same label
    # 2. Only a few frames at the end got different labels
    # 3. OR labels are scattered but transitions are too close together
    
    if len(frame_boundaries) <= 2 and len(unique_labels) > 1:
        logger.warning(f"🔍 DETAILED: ⚠️ Only {len(frame_boundaries)} boundaries found despite {len(unique_labels)} unique labels!")
        logger.warning(f"🔍 DETAILED: This suggests labels are either:")
        logger.warning(f"  a) All clustered at the end (most frames = one label)")
        logger.warning(f"  b) Scattered but transitions are too close together")
        logger.warning(f"🔍 DETAILED: Trying alternative: find major contiguous regions")
        
        # Alternative: Find the largest contiguous regions for each label
        # Group consecutive frames with the same label
        contiguous_regions = []
        current_label = labels_array[0]
        region_start = 0
        
        for idx in range(1, n_frames):
            if labels_array[idx] != current_label:
                # End of current region
                region_length = idx - region_start
                if region_length >= min_frame_gap:
                    contiguous_regions.append((region_start, idx, current_label, region_length))
                # Start new region
                current_label = labels_array[idx]
                region_start = idx
        
        # Add final region
        region_length = n_frames - region_start
        if region_length >= min_frame_gap:
            contiguous_regions.append((region_start, n_frames, current_label, region_length))
        
        logger.info(f"🔍 DETAILED: Found {len(contiguous_regions)} contiguous regions (min_length={min_frame_gap})")
        
        if len(contiguous_regions) > 1:
            # Use boundaries from contiguous regions
            frame_boundaries = [0]
            for start, end, label, length in contiguous_regions:
                if start > 0 and start - frame_boundaries[-1] >= min_frame_gap:
                    frame_boundaries.append(start)
                if end < n_frames and end - frame_boundaries[-1] >= min_frame_gap:
                    frame_boundaries.append(end)
            frame_boundaries.append(n_frames)
            frame_boundaries = sorted(set(frame_boundaries))
            logger.info(f"🔍 DETAILED: Using {len(frame_boundaries)} boundaries from contiguous regions")
        else:
            # Clustering failed - use uniform segmentation based on song duration
            # This is better than having one huge "bridge" segment
            logger.warning(f"🔍 DETAILED: ⚠️ Clustering failed to find meaningful structure, using uniform segmentation")
            # Aim for 4-8 segments based on duration (similar to clip boundaries)
            n_segments = max(4, min(8, int(duration / 45)))  # ~45s per segment for structure
            segment_length = duration / n_segments
            frame_boundaries = [0]
            for i in range(1, n_segments):
                boundary_frame = int((i * segment_length * sr) / hop_length)
                if boundary_frame - frame_boundaries[-1] >= min_frame_gap:
                    frame_boundaries.append(boundary_frame)
            frame_boundaries.append(n_frames)
            logger.info(f"🔍 DETAILED: Created {len(frame_boundaries)} uniform segments (n_segments={n_segments}, segment_length={segment_length:.1f}s)")
    
    logger.info(f"🔍 DETAILED: frame_boundaries: {frame_boundaries[:15]}... (total: {len(frame_boundaries)})")
    
    # Convert frame indices to seconds
    boundary_times: List[float] = []
    for frame_idx in frame_boundaries:
        time_sec = float(frame_idx * hop_length / sr)
        boundary_times.append(time_sec)
    
    boundary_times[0] = 0.0
    boundary_times[-1] = float(duration)
    
    logger.info(f"🔍 DETAILED: boundary_times: {boundary_times[:15]}... (total: {len(boundary_times)})")
    
    # Create segments
    segments: List[Tuple[float, float, int]] = []
    for i in range(len(frame_boundaries) - 1):
        start_frame = frame_boundaries[i]
        end_frame = frame_boundaries[i + 1]
        if end_frame <= start_frame:
            logger.warning(f"🔍 DETAILED: Skipping invalid segment: start_frame={start_frame}, end_frame={end_frame}")
            continue
        
        start_time = max(0.0, min(boundary_times[i], duration))
        end_time = max(start_time, min(boundary_times[i + 1], duration))
        if end_time - start_time <= 0:
            logger.warning(f"🔍 DETAILED: Skipping zero-duration segment: {start_time:.2f}-{end_time:.2f}s")
            continue
        
        # Determine the dominant label in this segment
        frame_slice = labels_array[start_frame:end_frame]
        if frame_slice.size == 0:
            logger.warning(f"🔍 DETAILED: Skipping empty frame slice: {start_frame}-{end_frame}")
            continue
        
        counts = np.bincount(frame_slice)
        label = int(np.argmax(counts))
        segments.append((start_time, end_time, label))
        logger.debug(f"🔍 DETAILED: Segment {i}: {start_time:.2f}-{end_time:.2f}s, label={label}, frames={start_frame}-{end_frame}")
    
    if not segments:
        logger.warning(f"🔍 DETAILED: No segments created, using fallback single segment")
        segments.append((0.0, float(duration), int(labels_array[0]) if labels_array.size > 0 else 0))
    
    logger.info(f"🔍 DETAILED: Created {len(segments)} segments: {[(f'{s[0]:.2f}', f'{s[1]:.2f}', s[2]) for s in segments[:15]]}")
    
    return segments


def analyze_structure(
    y: np.ndarray,
    sr: int,
    beat_timestamps: List[float],
    duration: float
) -> Tuple[List[SongStructure], bool]:
    """
    Classify song sections with energy levels.
    
    Args:
        y: Audio signal array
        sr: Sample rate
        beat_timestamps: List of beat timestamps
        duration: Total duration in seconds
        
    Returns:
        Tuple of (List of SongStructure objects, fallback_used flag)
        fallback_used is True if uniform segmentation fallback was used
    """
    logger.info(
        f"Starting structure analysis: duration={duration:.2f}s, "
        f"samples={len(y)}, sample_rate={sr}Hz, "
        f"beats_provided={len(beat_timestamps)}"
    )
    
    try:
        # 1. Extract chroma features
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=512)
        logger.info(
            f"Extracted chroma features: shape={chroma.shape}, "
            f"time_frames={chroma.shape[1]}, "
            f"chroma_bins={chroma.shape[0]}"
        )
        
        # 2. Build recurrence matrix (self-similarity matrix)
        # Transpose chroma to get time frames as rows
        chroma_t = chroma.T
        
        # Compute cosine similarity matrix
        # Normalize chroma vectors
        chroma_norm = chroma_t / (np.linalg.norm(chroma_t, axis=1, keepdims=True) + 1e-10)
        similarity_matrix = np.dot(chroma_norm, chroma_norm.T)
        
        logger.debug(f"Computed similarity matrix: shape={similarity_matrix.shape}")
        
        # 3. Segment detection using agglomerative clustering
        # Convert similarity to distance (1 - similarity)
        distance_matrix = 1 - similarity_matrix
        
        # Validate distance matrix before clustering
        n_frames = distance_matrix.shape[0]
        logger.info(f"Distance matrix shape: {distance_matrix.shape}, frames: {n_frames}")
        
        # Check for invalid values
        if np.any(np.isnan(distance_matrix)) or np.any(np.isinf(distance_matrix)):
            logger.error(
                f"Distance matrix contains NaN or Inf values. "
                f"NaN count: {np.sum(np.isnan(distance_matrix))}, "
                f"Inf count: {np.sum(np.isinf(distance_matrix))}"
            )
            raise ValueError("Invalid values in distance matrix")
        
        # Check matrix symmetry (required for precomputed metric)
        if not np.allclose(distance_matrix, distance_matrix.T, rtol=1e-5):
            logger.warning("Distance matrix is not symmetric, forcing symmetry")
            distance_matrix = (distance_matrix + distance_matrix.T) / 2
        
        # Add temporal penalty to distance matrix to encourage temporal contiguity
        # Frames that are far apart in time should be less likely to cluster together
        # This helps enforce that segments are contiguous
        frame_indices = np.arange(n_frames)
        temporal_dist_matrix = np.abs(frame_indices[:, None] - frame_indices[None, :]) / n_frames
        # Increase temporal penalty to strongly encourage contiguous segments
        # This prevents distant frames from clustering together even if harmonically similar
        # 0.35 = 35% weight on temporal proximity vs 65% on chroma similarity
        temporal_penalty = temporal_dist_matrix * 0.35
        
        # Combine distance with temporal penalty
        # This makes distant frames less likely to cluster together
        constrained_distance = distance_matrix + temporal_penalty
        
        logger.info(
            f"Distance matrix stats: min={np.min(distance_matrix):.4f}, "
            f"max={np.max(distance_matrix):.4f}, "
            f"mean={np.mean(distance_matrix):.4f}, "
            f"std={np.std(distance_matrix):.4f}"
        )
        logger.info(
            f"Constrained distance stats: min={np.min(constrained_distance):.4f}, "
            f"max={np.max(constrained_distance):.4f}, "
            f"mean={np.mean(constrained_distance):.4f}, "
            f"std={np.std(constrained_distance):.4f}"
        )
        
        # Use agglomerative clustering on temporally-constrained distance matrix
        # Determine number of clusters based on duration (rough estimate)
        # Request fewer clusters to encourage longer segments
        # For 32s: int(32/45) = 0, clamped to 2 clusters
        # For 90s: int(90/45) = 2 clusters
        # For 180s: int(180/45) = 4 clusters
        n_segments = max(2, min(4, int(duration / 45)))  # ~45s per segment target
        
        logger.info(
            f"Clustering setup: target_segments={n_segments} (based on duration={duration:.2f}s / 30s), "
            f"available_frames={n_frames}, "
            f"matrix_stats: min={np.min(distance_matrix):.4f}, "
            f"max={np.max(distance_matrix):.4f}, "
            f"mean={np.mean(distance_matrix):.4f}, "
            f"std={np.std(distance_matrix):.4f}"
        )
        
        # Validate we have enough frames for clustering
        if n_frames < n_segments:
            logger.warning(
                f"⚠️ Insufficient frames for clustering: {n_frames} frames < {n_segments} clusters. "
                f"Reducing clusters to {n_frames} or using fallback. "
                f"This may indicate audio is too short or chroma extraction issues."
            )
            n_segments = max(2, n_frames - 1)  # Need at least 2 samples per cluster
        
        logger.info(f"Attempting temporally-constrained agglomerative clustering: n_clusters={n_segments}, n_frames={n_frames}")
        
        try:
            clustering = AgglomerativeClustering(
                n_clusters=n_segments,
                metric='precomputed',
                linkage='complete'
            )
            labels = clustering.fit_predict(constrained_distance)
            unique_labels, label_counts = np.unique(labels, return_counts=True)
            logger.info(f"🔍 DETAILED: Clustering successful: {len(unique_labels)} unique segments detected")
            logger.info(f"🔍 DETAILED: Label distribution: {dict(zip(unique_labels, label_counts))}")
            logger.info(f"🔍 DETAILED: First 20 labels: {labels[:20]}")
            logger.info(f"🔍 DETAILED: Last 20 labels: {labels[-20:]}")
            logger.info(f"🔍 DETAILED: Label changes: {np.sum(np.diff(labels) != 0)} transitions detected")
        except ValueError as e:
            error_msg = str(e)
            logger.error(
                f"Agglomerative clustering failed (ValueError): {error_msg}. "
                f"Diagnostics: n_frames={n_frames}, n_segments={n_segments}, "
                f"matrix_shape={distance_matrix.shape}, "
                f"matrix_min={np.min(distance_matrix):.4f}, "
                f"matrix_max={np.max(distance_matrix):.4f}, "
                f"matrix_mean={np.mean(distance_matrix):.4f}. "
                f"Falling back to uniform segmentation."
            )
            # Fallback: simple segmentation
            use_fallback = True
        except Exception as e:
            error_type = type(e).__name__
            logger.error(
                f"Agglomerative clustering failed ({error_type}): {str(e)}. "
                f"Diagnostics: n_frames={n_frames}, n_segments={n_segments}, "
                f"matrix_shape={distance_matrix.shape}, duration={duration:.2f}s. "
                f"Falling back to uniform segmentation."
            )
            # Fallback: simple segmentation
            use_fallback = True
        else:
            use_fallback = False
        
        if use_fallback:
            # If audio is empty or too short, return single segment
            if len(y) == 0 or duration <= 0:
                logger.warning("Empty audio detected, returning single-segment fallback")
                return ([SongStructure(
                    type="verse",
                    start=0.0,
                    end=max(duration, 0.1),  # Ensure at least 0.1s
                    energy="medium"
                )], True)
            
            # For fallback, create fewer, longer segments for better musical structure
            # Aim for 15-20s per segment (better for chorus/verse detection)
            # This allows clip boundaries to create multiple varied clips per segment
            n_segments = max(2, min(6, int(duration / 18)))
            segment_length = duration / n_segments
            segments = []
            for i in range(n_segments):
                start = i * segment_length
                end = (i + 1) * segment_length if i < n_segments - 1 else duration
                segments.append((start, end, i))
            
            # Classify segments
            try:
                rms_features = librosa.feature.rms(y=y)[0]
                centroid_features = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
                max_rms = np.max(rms_features) if len(rms_features) > 0 else 1.0
                max_centroid = np.max(centroid_features) if len(centroid_features) > 0 else 5000.0
            except Exception:
                # If feature extraction fails, use defaults
                max_rms = 1.0
                max_centroid = 5000.0
            
            song_structure = []
            for i, (start, end, label) in enumerate(segments):
                start_idx = int(start * sr)
                end_idx = int(end * sr)
                y_segment = y[start_idx:end_idx]
                
                if len(y_segment) == 0:
                    # Skip empty segments, but ensure we have at least one
                    continue
                
                energy = _calculate_segment_energy(y_segment, sr, max_rms, max_centroid)
                
                # Classify type
                if i == 0 and end - start < 15 and energy < 0.4:
                    seg_type = "intro"
                elif i == len(segments) - 1 and end - start < 15 and energy < 0.4:
                    seg_type = "outro"
                elif energy > 0.7:
                    seg_type = "chorus"
                elif energy < 0.4:
                    seg_type = "verse"
                else:
                    seg_type = "bridge"
                
                # Map energy to level
                if energy < 0.4:
                    energy_level = "low"
                elif energy > 0.7:
                    energy_level = "high"
                else:
                    energy_level = "medium"

                # Create segment object
                segment_obj = SongStructure(
                    type=seg_type,
                    start=start,
                    end=end,
                    energy=energy_level
                )

                # Calculate beat intensity if beat_timestamps are provided
                if beat_timestamps:
                    beat_intensity = calculate_segment_beat_intensity(
                        segment_obj, beat_timestamps, y, sr
                    )
                    segment_obj.beat_intensity = beat_intensity

                song_structure.append(segment_obj)
            
            # Ensure we return at least one segment
            if len(song_structure) == 0:
                logger.warning("No segments generated in fallback, returning single-segment")
                return ([SongStructure(
                    type="verse",
                    start=0.0,
                    end=max(duration, 0.1),
                    energy="medium"
                )], True)
            
            logger.warning(
                f"⚠️ STRUCTURE ANALYSIS FALLBACK ACTIVATED ⚠️ "
                f"Clustering failed - using uniform segmentation instead. "
                f"Generated {len(song_structure)} evenly-divided segments: "
                f"{[f'{s.type}({s.start:.1f}-{s.end:.1f}s, {s.energy})' for s in song_structure]}. "
                f"Segment length={segment_length:.2f}s, n_segments={n_segments}. "
                f"Check error logs above for clustering failure details. "
                f"This usually indicates: (1) Audio too short ({duration:.2f}s), "
                f"(2) Insufficient chroma features (n_frames={n_frames}), "
                f"or (3) Matrix computation issues."
            )
            return (song_structure, True)
        
        hop_length = 512
        logger.info(
            f"Converting {len(labels)} frame labels to time segments using hop_length={hop_length}"
        )
        segment_windows = _labels_to_segments(labels, sr, duration, hop_length=hop_length)
        
        logger.info(
            f"✅ Segment boundaries detected: {len(segment_windows)} segments "
            f"derived from {len(labels)} frames. "
            f"Full list={[f'{s[0]:.1f}-{s[1]:.1f}s(label={s[2]})' for s in segment_windows]}"
        )
        
        # 4. Classify segments
        # Calculate max values for normalization (use full track)
        rms_full = librosa.feature.rms(y=y)[0]
        centroid_full = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        max_rms = float(np.max(rms_full)) if len(rms_full) > 0 else 1.0
        max_centroid = float(np.max(centroid_full)) if len(centroid_full) > 0 else 5000.0
        
        logger.info(
            f"Energy normalization values: max_rms={max_rms:.4f}, max_centroid={max_centroid:.2f}Hz"
        )
        
        song_structure = []
        for i, (start, end, label) in enumerate(segment_windows):
            # Skip zero-duration segments
            if end <= start:
                logger.warning(f"Skipping zero-duration segment: {start:.1f}-{end:.1f}s")
                continue
            
            start_idx = int(start * sr)
            end_idx = int(end * sr)
            y_segment = y[start_idx:end_idx]
            
            if len(y_segment) == 0:
                logger.warning(f"Skipping empty segment: {start:.1f}-{end:.1f}s (no audio samples)")
                continue
            
            energy = _calculate_segment_energy(y_segment, sr, max_rms, max_centroid)
            
            # Classify type using heuristics
            segment_duration = end - start
            n_segments = len(segment_windows)
            
            # If we only have 2 segments, the clustering likely failed
            # Use position-based classification instead of defaulting to "bridge"
            if n_segments <= 2:
                # For very few segments, use simple position-based classification
                if i == 0:
                    # First segment: could be intro or verse
                    if segment_duration < 20 and energy < 0.4:
                        seg_type = "intro"
                    else:
                        seg_type = "verse"  # Default first segment to verse, not bridge
                elif i == n_segments - 1:
                    # Last segment: outro if short and low energy, otherwise verse
                    if segment_duration < 20 and energy < 0.4:
                        seg_type = "outro"
                    else:
                        seg_type = "verse"
                else:
                    seg_type = "verse"
            else:
                # Normal classification for multiple segments
                if i == 0 and segment_duration < 15 and energy < 0.4:
                    seg_type = "intro"
                elif i == n_segments - 1 and segment_duration < 15 and energy < 0.4:
                    seg_type = "outro"
                elif energy > 0.7:
                    seg_type = "chorus"
                elif energy < 0.4:
                    seg_type = "verse"
                else:
                    # For medium energy, alternate between verse and chorus based on position
                    # This prevents everything from being labeled "bridge"
                    if i % 2 == 0:
                        seg_type = "verse"
                    else:
                        seg_type = "chorus"
            
            # Map energy to level
            if energy < 0.4:
                energy_level = "low"
            elif energy > 0.7:
                energy_level = "high"
            else:
                energy_level = "medium"
            
            # Create segment object
            segment_obj = SongStructure(
                type=seg_type,
                start=start,
                end=end,
                energy=energy_level
            )

            # Calculate beat intensity if beat_timestamps are provided
            if beat_timestamps:
                beat_intensity = calculate_segment_beat_intensity(
                    segment_obj, beat_timestamps, y, sr
                )
                segment_obj.beat_intensity = beat_intensity
                logger.debug(
                    f"Segment {i}: {start:.1f}-{end:.1f}s (duration={segment_duration:.1f}s), "
                    f"energy={energy:.3f} ({energy_level}), type={seg_type}, beat_intensity={beat_intensity}"
                )
            else:
                logger.debug(
                    f"Segment {i}: {start:.1f}-{end:.1f}s (duration={segment_duration:.1f}s), "
                    f"energy={energy:.3f} ({energy_level}), type={seg_type}"
                )

            song_structure.append(segment_obj)
        
        logger.info(
            f"Structure analysis complete: {len(song_structure)} segments detected via clustering. "
            f"Segments: {[f'{s.type}({s.start:.1f}-{s.end:.1f}s, {s.energy})' for s in song_structure]}"
        )
        return (song_structure, False)  # Clustering succeeded, no fallback used
        
    except ValueError as e:
        # This is a clustering validation error - log detailed diagnostics
        logger.error(
            f"Structure analysis failed due to clustering validation error: {str(e)}. "
            f"Audio diagnostics: duration={duration:.2f}s, samples={len(y)}, "
            f"sample_rate={sr}Hz. This usually means: "
            f"(1) Audio too short for clustering, (2) Invalid chroma features, "
            f"or (3) Matrix computation issues."
        )
        # Fallback: single segment covering entire duration
        logger.warning("Using fallback single-segment structure")
        return ([SongStructure(
            type="verse",
            start=0.0,
            end=duration,
            energy="medium"
        )], True)
    except Exception as e:
        error_type = type(e).__name__
        logger.error(
            f"Structure analysis failed ({error_type}): {str(e)}. "
            f"Audio diagnostics: duration={duration:.2f}s, samples={len(y)}, "
            f"sample_rate={sr}Hz"
        )
        # Fallback: single segment covering entire duration
        logger.warning("Using fallback single-segment structure")
        return ([SongStructure(
            type="verse",
            start=0.0,
            end=duration,
            energy="medium"
        )], True)


def analyze_structure_from_clips(
    y: np.ndarray,
    sr: int,
    clip_boundaries: List[ClipBoundary],
    duration: float,
    beat_timestamps: List[float] = None
) -> Tuple[List[SongStructure], bool]:
    """
    Analyze song structure using clip boundaries as the base segments.
    
    This ensures structure segments align perfectly with clip boundaries,
    which are beat-aligned. Each clip boundary is then classified as
    verse/chorus/bridge/etc. based on its audio features.
    
    Args:
        y: Audio signal array
        sr: Sample rate
        clip_boundaries: List of ClipBoundary objects (beat-aligned)
        duration: Total duration in seconds
        
    Returns:
        Tuple of (List of SongStructure objects, fallback_used flag)
    """
    logger.info(
        f"Starting structure analysis from clip boundaries: "
        f"duration={duration:.2f}s, clips={len(clip_boundaries)}"
    )
    
    if not clip_boundaries or len(clip_boundaries) == 0:
        logger.warning("No clip boundaries provided, using fallback single segment")
        return ([SongStructure(
            type="verse",
            start=0.0,
            end=duration,
            energy="medium"
        )], True)
    
    try:
        # Calculate max values for normalization (use full track)
        rms_full = librosa.feature.rms(y=y)[0]
        centroid_full = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        max_rms = float(np.max(rms_full)) if len(rms_full) > 0 else 1.0
        max_centroid = float(np.max(centroid_full)) if len(centroid_full) > 0 else 5000.0
        
        logger.info(
            f"Energy normalization values: max_rms={max_rms:.4f}, max_centroid={max_centroid:.2f}Hz"
        )
        
        song_structure = []
        for i, clip in enumerate(clip_boundaries):
            start = clip.start
            end = clip.end
            segment_duration = end - start
            
            # Skip invalid segments
            if end <= start or segment_duration <= 0:
                logger.warning(f"Skipping invalid clip boundary: {start:.1f}-{end:.1f}s")
                continue
            
            # Extract audio segment
            start_idx = int(start * sr)
            end_idx = int(end * sr)
            y_segment = y[start_idx:end_idx]
            
            if len(y_segment) == 0:
                logger.warning(f"Skipping empty segment: {start:.1f}-{end:.1f}s (no audio samples)")
                continue
            
            # Calculate energy for this segment
            energy = _calculate_segment_energy(y_segment, sr, max_rms, max_centroid)
            
            # Classify type using heuristics based on position and energy
            n_clips = len(clip_boundaries)
            
            if i == 0 and segment_duration < 20 and energy < 0.4:
                seg_type = "intro"
            elif i == n_clips - 1 and segment_duration < 20 and energy < 0.4:
                seg_type = "outro"
            elif energy > 0.7:
                seg_type = "chorus"
            elif energy < 0.4:
                seg_type = "verse"
            else:
                # Medium energy: alternate between verse and chorus based on position
                # This prevents everything from being labeled "bridge"
                if i % 2 == 0:
                    seg_type = "verse"
                else:
                    seg_type = "chorus"
            
            # Map energy to level
            if energy < 0.4:
                energy_level = "low"
            elif energy > 0.7:
                energy_level = "high"
            else:
                energy_level = "medium"
            
            # Calculate beat intensity for this segment
            segment_obj = SongStructure(
                type=seg_type,
                start=start,
                end=end,
                energy=energy_level
            )
            
            # Calculate beat intensity if beat_timestamps are provided
            if beat_timestamps:
                beat_intensity = calculate_segment_beat_intensity(
                    segment_obj, beat_timestamps, y, sr
                )
                segment_obj.beat_intensity = beat_intensity
                logger.debug(
                    f"Clip {i+1}/{n_clips}: {start:.1f}-{end:.1f}s (duration={segment_duration:.1f}s), "
                    f"energy={energy:.3f} ({energy_level}), type={seg_type}, beat_intensity={beat_intensity}"
                )
            else:
                logger.debug(
                    f"Clip {i+1}/{n_clips}: {start:.1f}-{end:.1f}s (duration={segment_duration:.1f}s), "
                    f"energy={energy:.3f} ({energy_level}), type={seg_type}"
                )
            
            song_structure.append(segment_obj)
        
        logger.info(
            f"Structure analysis complete: {len(song_structure)} segments "
            f"(aligned with {len(clip_boundaries)} clip boundaries). "
            f"Segments: {[f'{s.type}({s.start:.1f}-{s.end:.1f}s, {s.energy})' for s in song_structure[:10]]}..."
        )
        return (song_structure, False)  # No fallback used - based on clip boundaries
        
    except Exception as e:
        error_type = type(e).__name__
        logger.error(
            f"Structure analysis from clips failed ({error_type}): {str(e)}. "
            f"Audio diagnostics: duration={duration:.2f}s, samples={len(y)}, "
            f"sample_rate={sr}Hz, clips={len(clip_boundaries)}"
        )
        # Fallback: create structure from clip boundaries with default classification
        logger.warning("Using fallback: creating structure from clip boundaries with default classification")
        song_structure = []
        for i, clip in enumerate(clip_boundaries):
            seg_type = "verse" if i % 2 == 0 else "chorus"
            if i == 0:
                seg_type = "intro"
            elif i == len(clip_boundaries) - 1:
                seg_type = "outro"
            
            segment_obj = SongStructure(
                type=seg_type,
                start=clip.start,
                end=clip.end,
                energy="medium"
            )
            
            # Calculate beat intensity if beat_timestamps are provided
            if beat_timestamps:
                beat_intensity = calculate_segment_beat_intensity(
                    segment_obj, beat_timestamps, y, sr
                )
                segment_obj.beat_intensity = beat_intensity
            
            song_structure.append(segment_obj)
        return (song_structure, True)


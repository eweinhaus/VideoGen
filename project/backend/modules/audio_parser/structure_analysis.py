"""
Song structure classification.

Analyze song structure (intro/verse/chorus/bridge/outro) using chroma features and clustering.
"""

import numpy as np
from typing import List

import librosa
from sklearn.cluster import AgglomerativeClustering

from shared.models.audio import SongStructure
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


def analyze_structure(
    y: np.ndarray,
    sr: int,
    beat_timestamps: List[float],
    duration: float
) -> List[SongStructure]:
    """
    Classify song sections with energy levels.
    
    Args:
        y: Audio signal array
        sr: Sample rate
        beat_timestamps: List of beat timestamps
        duration: Total duration in seconds
        
    Returns:
        List of SongStructure objects
    """
    try:
        # 1. Extract chroma features
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=512)
        logger.debug(f"Extracted chroma features: shape={chroma.shape}")
        
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
        
        # Use agglomerative clustering on distance matrix
        # Determine number of clusters based on duration (rough estimate)
        # Aim for 3-8 segments for typical songs
        n_segments = max(3, min(8, int(duration / 30)))  # ~30s per segment
        
        # Validate we have enough frames for clustering
        if n_frames < n_segments:
            logger.warning(
                f"Insufficient frames for clustering: {n_frames} frames < {n_segments} clusters. "
                f"Reducing clusters to {n_frames} or using fallback."
            )
            n_segments = max(2, n_frames - 1)  # Need at least 2 samples per cluster
        
        logger.info(f"Attempting clustering with {n_segments} clusters on {n_frames} frames")
        
        try:
            clustering = AgglomerativeClustering(
                n_clusters=n_segments,
                metric='precomputed',
                linkage='average'
            )
            labels = clustering.fit_predict(distance_matrix)
            logger.info(f"Clustering successful: {len(np.unique(labels))} unique segments detected")
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
                return [SongStructure(
                    type="verse",
                    start=0.0,
                    end=max(duration, 0.1),  # Ensure at least 0.1s
                    energy="medium"
                )]
            
            n_segments = max(3, min(8, int(duration / 30)))
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
                
                song_structure.append(SongStructure(
                    type=seg_type,
                    start=start,
                    end=end,
                    energy=energy_level
                ))
            
            # Ensure we return at least one segment
            if len(song_structure) == 0:
                logger.warning("No segments generated in fallback, returning single-segment")
                return [SongStructure(
                    type="verse",
                    start=0.0,
                    end=max(duration, 0.1),
                    energy="medium"
                )]
            
            logger.warning(
                f"⚠️ STRUCTURE ANALYSIS FALLBACK ACTIVATED ⚠️ "
                f"Clustering failed - using uniform segmentation instead. "
                f"Generated {len(song_structure)} evenly-divided segments: "
                f"{[f'{s.start:.1f}-{s.end:.1f}s' for s in song_structure]}. "
                f"Check error logs above for clustering failure details. "
                f"This usually indicates: (1) Audio too short, (2) Insufficient chroma features, "
                f"or (3) Matrix computation issues."
            )
            return song_structure
        
        # Convert frame labels to time segments
        # Map each frame to its time position
        hop_length = 512
        frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)
        
        # Find segment boundaries (where label changes)
        segment_boundaries = [0.0]
        for i in range(1, len(labels)):
            if labels[i] != labels[i-1]:
                segment_boundaries.append(frame_times[i])
        segment_boundaries.append(duration)
        
        # Create segments from boundaries
        segments = []
        for i in range(len(segment_boundaries) - 1):
            start = segment_boundaries[i]
            end = segment_boundaries[i + 1]
            segments.append((start, end, labels[int((start + end) / 2 * sr / hop_length)] if len(labels) > 0 else 0))
        
        # 4. Classify segments
        # Calculate max values for normalization
        max_rms = np.max(librosa.feature.rms(y=y)[0])
        max_centroid = np.max(librosa.feature.spectral_centroid(y=y, sr=sr)[0])
        
        song_structure = []
        for i, (start, end, label) in enumerate(segments):
            start_idx = int(start * sr)
            end_idx = int(end * sr)
            y_segment = y[start_idx:end_idx]
            
            if len(y_segment) == 0:
                continue
            
            energy = _calculate_segment_energy(y_segment, sr, max_rms, max_centroid)
            
            # Classify type using heuristics
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
            
            song_structure.append(SongStructure(
                type=seg_type,
                start=start,
                end=end,
                energy=energy_level
            ))
        
        logger.info(
            f"Structure analysis complete: {len(song_structure)} segments detected via clustering. "
            f"Segments: {[f'{s.type}({s.start:.1f}-{s.end:.1f}s, {s.energy})' for s in song_structure]}"
        )
        return song_structure
        
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
        return [SongStructure(
            type="verse",
            start=0.0,
            end=duration,
            energy="medium"
        )]
    except Exception as e:
        error_type = type(e).__name__
        logger.error(
            f"Structure analysis failed ({error_type}): {str(e)}. "
            f"Audio diagnostics: duration={duration:.2f}s, samples={len(y)}, "
            f"sample_rate={sr}Hz"
        )
        # Fallback: single segment covering entire duration
        logger.warning("Using fallback single-segment structure")
        return [SongStructure(
            type="verse",
            start=0.0,
            end=duration,
            energy="medium"
        )]


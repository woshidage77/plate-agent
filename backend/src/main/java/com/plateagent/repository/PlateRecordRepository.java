package com.plateagent.repository;

import com.plateagent.entity.PlateRecord;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;

public interface PlateRecordRepository extends JpaRepository<PlateRecord, Long> {

    Page<PlateRecord> findByPlateNumberContaining(String plateNumber, Pageable pageable);

    Page<PlateRecord> findByStatus(String status, Pageable pageable);

    Page<PlateRecord> findByBlacklistHitTrue(Pageable pageable);

    List<PlateRecord> findByCreatedAtBetween(LocalDateTime start, LocalDateTime end);

    @Query("SELECT p.plateNumber, COUNT(p) FROM PlateRecord p " +
           "WHERE p.createdAt BETWEEN :start AND :end " +
           "GROUP BY p.plateNumber ORDER BY COUNT(p) DESC")
    List<Object[]> findTopPlates(@Param("start") LocalDateTime start,
                                  @Param("end") LocalDateTime end,
                                  Pageable pageable);

    long countByCreatedAtBetween(LocalDateTime start, LocalDateTime end);

    long countByStatusAndCreatedAtBetween(String status, LocalDateTime start, LocalDateTime end);

    @Query("SELECT AVG(p.avgConfidence) FROM PlateRecord p " +
           "WHERE p.createdAt BETWEEN :start AND :end")
    Double avgConfidenceBetween(@Param("start") LocalDateTime start,
                                @Param("end") LocalDateTime end);
}
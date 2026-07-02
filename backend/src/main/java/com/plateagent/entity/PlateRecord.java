package com.plateagent.entity;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "plate_records", indexes = {
    @Index(name = "idx_plate_number", columnList = "plateNumber"),
    @Index(name = "idx_created_at", columnList = "createdAt")
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PlateRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 识别出的车牌号 */
    @Column(nullable = false, length = 10)
    private String plateNumber;

    /** 原始图片路径 */
    @Column(length = 500)
    private String imagePath;

    /** 车牌颜色 */
    @Column(length = 20)
    private String plateColor;

    /** 平均置信度 */
    private Double avgConfidence;

    /** 是否命中黑名单 */
    private Boolean blacklistHit;

    /** 黑名单类型（套牌/违章/盗抢等） */
    @Column(length = 50)
    private String blacklistType;

    /** 识别方式：SVM / SVM+LLM */
    @Column(length = 20)
    private String recognizeMethod;

    /** 处理耗时(ms) */
    private Long processTimeMs;

    /** 识别状态：success / partial / failed */
    @Column(length = 20)
    private String status;

    /** 错误信息 */
    @Column(length = 1000)
    private String errorMessage;

    /** 完整识别结果 JSON */
    @Column(columnDefinition = "TEXT")
    private String rawResult;

    @Column(updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }
}
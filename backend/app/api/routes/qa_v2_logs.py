# 添加在 qa_v2.py 文件末尾，在所有其他路由之后


@router.get("/logs", response_model=Dict[str, Any])
async def get_logs(
    level: Optional[str] = None,
    event_type: Optional[str] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """查询 QA 系统日志
    
    支持按级别、事件类型、trace_id、session_id 过滤
    """
    try:
        # 从日志文件或内存中读取日志
        # 这里简化实现，实际应该从文件或数据库读取
        logs = []
        
        # TODO: 实现从日志文件读取的逻辑
        # 1. 如果配置了 log_file，读取 JSONL 文件
        # 2. 按参数过滤
        # 3. 支持分页
        
        return {
            "logs": logs,
            "total": len(logs),
            "limit": limit,
            "offset": offset,
            "filters": {
                "level": level,
                "event_type": event_type,
                "trace_id": trace_id,
                "session_id": session_id,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")



@router.get("/logs/trace/{trace_id}", response_model=Dict[str, Any])
async def get_trace_logs(
    trace_id: str,
) -> Dict[str, Any]:
    """获取特定 Trace ID 的所有日志"""
    try:
        # 使用日志分析器分析特定 trace
        from agent.core.qa_log_analyzer import QALogAnalyzer
        
        analyzer = QALogAnalyzer()
        analyzer.load_logs(limit=10000)  # 加载足够多的日志
        
        analysis = analyzer.analyze_trace(trace_id)
        
        if "error" in analysis:
            raise HTTPException(status_code=404, detail=analysis["error"])
        
        return {
            "trace_id": trace_id,
            "analysis": analysis,
            "logs": analyzer.trace_map.get(trace_id, [])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze trace: {str(e)}")

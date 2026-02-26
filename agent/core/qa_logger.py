"""
QA System Logging Architecture

Provides comprehensive logging for multi-agent QA system with:
- Hierarchical log levels (DEBUG, INFO, WARN, ERROR, CRITICAL)
- Structured JSON logging with context propagation
- Trace ID based request tracking
- Agent/Tool/DAG execution flow logging
- Performance metrics collection

Usage:
    from agent.core.qa_logger import get_qa_logger, QAOperationContext
    
    logger = get_qa_logger()
    
    with QAOperationContext(trace_id="trace_123", operation="qa_request") as ctx:
        logger.info("Processing QA request", query="hello", route="FAST_PATH")
        # ... agent execution ...
        logger.agent_step("PromptAgent", "route_decision", route="FAST_PATH", reason="short_query")
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class QALogLevel(Enum):
    """QA System specific log levels"""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"
    
    # Operation specific levels
    AGENT_STEP = "agent_step"      # Agent execution step
    TOOL_CALL = "tool_call"        # Tool invocation
    DAG_EVENT = "dag_event"        # DAG execution event
    ROUTER_DECISION = "router_dec"  # Router/Gate decision
    CONTEXT_CHANGE = "ctx_change"  # Context modification


class QAOperationContext:
    """
    Context manager for QA operations with automatic trace ID generation
    and structured logging context.
    """
    
    _current_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
        'qa_current_context', default=None
    )
    
    def __init__(
        self,
        trace_id: Optional[str] = None,
        operation: str = "unknown",
        session_id: Optional[str] = None,
        doc_id: Optional[str] = None,
        user_query: Optional[str] = None,
        parent_context: Optional[Dict[str, Any]] = None
    ):
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:16]}"
        self.operation = operation
        self.session_id = session_id
        self.doc_id = doc_id
        self.user_query = user_query
        self.parent_context = parent_context
        
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.token = None
    
    def __enter__(self) -> "QAOperationContext":
        """Enter context and set current context variable"""
        self.start_time = time.time()
        
        context_data = {
            "trace_id": self.trace_id,
            "operation": self.operation,
            "session_id": self.session_id,
            "doc_id": self.doc_id,
            "user_query": self.user_query,
            "start_time": self.start_time,
            "parent_context": self.parent_context,
        }
        
        self.token = self._current_context.set(context_data)
        
        # Log context entry
        get_qa_logger()._log_structured(
            level=QALogLevel.INFO,
            message=f"Started operation: {self.operation}",
            context=context_data,
            event_type="operation_start"
        )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and log completion"""
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000 if self.start_time else 0
        
        context_data = self._current_context.get() or {}
        context_data["duration_ms"] = duration_ms
        context_data["end_time"] = self.end_time
        
        if exc_type:
            context_data["error"] = {
                "type": exc_type.__name__,
                "message": str(exc_val)
            }
            level = QALogLevel.ERROR
            message = f"Operation failed: {self.operation} - {exc_val}"
            event_type = "operation_error"
        else:
            level = QALogLevel.INFO
            message = f"Completed operation: {self.operation}"
            event_type = "operation_end"
        
        get_qa_logger()._log_structured(
            level=level,
            message=message,
            context=context_data,
            event_type=event_type
        )
        
        if self.token:
            self._current_context.reset(self.token)
    
    @classmethod
    def get_current(cls) -> Optional[Dict[str, Any]]:
        """Get current operation context data"""
        return cls._current_context.get()
    
    @classmethod
    def get_trace_id(cls) -> Optional[str]:
        """Get current trace ID"""
        ctx = cls._current_context.get()
        return ctx.get("trace_id") if ctx else None


class QALogger:
    """
    Structured logger for QA system with JSON output and context-aware logging.
    """
    
    def __init__(
        self,
        name: str = "qa_system",
        log_level: QALogLevel = QALogLevel.INFO,
        log_file: Optional[Union[str, Path]] = None,
        console_output: bool = True,
        structured: bool = True
    ):
        self.name = name
        self.log_level = log_level
        self.structured = structured
        self.log_file = Path(log_file) if log_file else None
        
        # Setup Python logger
        self._logger = logging.getLogger(name)
        self._logger.setLevel(self._level_to_python(log_level))
        self._logger.handlers = []  # Clear existing handlers
        
        # Console handler
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self._level_to_python(log_level))
            if structured:
                console_handler.setFormatter(self._create_json_formatter())
            else:
                console_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
            self._logger.addHandler(console_handler)
        
        # File handler
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(self._level_to_python(log_level))
            file_handler.setFormatter(self._create_json_formatter())
            self._logger.addHandler(file_handler)
    
    def _level_to_python(self, level: QALogLevel) -> int:
        """Convert QA log level to Python logging level"""
        mapping = {
            QALogLevel.DEBUG: logging.DEBUG,
            QALogLevel.INFO: logging.INFO,
            QALogLevel.WARN: logging.WARNING,
            QALogLevel.ERROR: logging.ERROR,
            QALogLevel.CRITICAL: logging.CRITICAL,
            # Operation levels map to INFO for Python logging
            QALogLevel.AGENT_STEP: logging.INFO,
            QALogLevel.TOOL_CALL: logging.INFO,
            QALogLevel.DAG_EVENT: logging.INFO,
            QALogLevel.ROUTER_DECISION: logging.INFO,
            QALogLevel.CONTEXT_CHANGE: logging.INFO,
        }
        return mapping.get(level, logging.INFO)
    
    def _create_json_formatter(self) -> logging.Formatter:
        """Create JSON formatter for structured logging"""
        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_data = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                # Add extra fields if present
                if hasattr(record, "event_type"):
                    log_data["event_type"] = record.event_type
                if hasattr(record, "trace_id"):
                    log_data["trace_id"] = record.trace_id
                if hasattr(record, "context"):
                    log_data["context"] = record.context
                if hasattr(record, "agent_name"):
                    log_data["agent_name"] = record.agent_name
                if hasattr(record, "tool_name"):
                    log_data["tool_name"] = record.tool_name
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_data, ensure_ascii=False)
        return JsonFormatter()
    
    def _log_structured(
        self,
        level: QALogLevel,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        event_type: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Internal structured logging method"""
        # Get current operation context
        op_ctx = QAOperationContext.get_current()
        trace_id = op_ctx.get("trace_id") if op_ctx else None
        
        # Create log record with extra fields
        extra = {
            "event_type": event_type,
            "trace_id": trace_id,
            "context": context,
        }
        if extra_fields:
            extra.update(extra_fields)
        
        # Log with Python logger
        python_level = self._level_to_python(level)
        self._logger.log(python_level, message, extra=extra)
    
    # Public logging methods
    def debug(self, message: str, **kwargs) -> None:
        self._log_structured(QALogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        self._log_structured(QALogLevel.INFO, message, **kwargs)
    
    def warn(self, message: str, **kwargs) -> None:
        self._log_structured(QALogLevel.WARN, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        self._log_structured(QALogLevel.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs) -> None:
        self._log_structured(QALogLevel.CRITICAL, message, **kwargs)
    
    # Operation-specific logging methods
    def agent_step(
        self,
        agent_name: str,
        step: str,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        **kwargs
    ) -> None:
        """Log an agent execution step"""
        context = {
            "agent_name": agent_name,
            "step": step,
            "inputs": inputs,
            "outputs": outputs,
            "duration_ms": duration_ms,
        }
        self._log_structured(
            QALogLevel.AGENT_STEP,
            f"Agent {agent_name} step: {step}",
            context=context,
            event_type="agent_step",
            extra_fields={"agent_name": agent_name},
            **kwargs
        )
    
    def tool_call(
        self,
        tool_name: str,
        action: str,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log a tool invocation"""
        context = {
            "tool_name": tool_name,
            "action": action,
            "inputs": inputs,
            "outputs": outputs,
            "duration_ms": duration_ms,
            "error": error,
        }
        level = QALogLevel.ERROR if error else QALogLevel.TOOL_CALL
        self._log_structured(
            level,
            f"Tool {tool_name}.{action} failed: {error}" if error else f"Tool {tool_name}.{action} completed",
            context=context,
            event_type="tool_call",
            extra_fields={"tool_name": tool_name},
            **kwargs
        )
    
    def dag_event(
        self,
        event_type: str,
        node_id: Optional[str] = None,
        node_type: Optional[str] = None,
        status: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        **kwargs
    ) -> None:
        """Log a DAG execution event"""
        context = {
            "event_type": event_type,
            "node_id": node_id,
            "node_type": node_type,
            "status": status,
            "inputs": inputs,
            "outputs": outputs,
            "error": error,
            "duration_ms": duration_ms,
        }
        level = QALogLevel.ERROR if error else QALogLevel.DAG_EVENT
        self._log_structured(
            level,
            f"DAG {event_type} {node_id}: {status}" if status else f"DAG {event_type} {node_id}",
            context=context,
            event_type=f"dag_{event_type}",
            extra_fields={"node_id": node_id, "event_type": event_type},
            **kwargs
        )
    
    def router_decision(
        self,
        query: str,
        route: str,
        reason: str,
        confidence: float,
        context_blocks: Optional[List[Dict]] = None,
        alternatives: Optional[List[str]] = None,
        **kwargs
    ) -> None:
        """Log a router/gate decision"""
        ctx = {
            "query": query,
            "route": route,
            "reason": reason,
            "confidence": confidence,
            "context_blocks_count": len(context_blocks) if context_blocks else 0,
            "alternatives": alternatives,
        }
        self._log_structured(
            QALogLevel.ROUTER_DECISION,
            f"Router chose {route} for query: {query[:50]}...",
            context=ctx,
            event_type="router_decision",
            extra_fields={"route": route, "confidence": confidence},
            **kwargs
        )
    
    def context_change(
        self,
        change_type: str,
        description: str,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        **kwargs
    ) -> None:
        """Log a context modification"""
        ctx = {
            "change_type": change_type,
            "description": description,
            "old_value": old_value,
            "new_value": new_value,
        }
        self._log_structured(
            QALogLevel.CONTEXT_CHANGE,
            f"Context {change_type}: {description}",
            context=ctx,
            event_type="context_change",
            extra_fields={"change_type": change_type},
            **kwargs
        )


# Global logger instance
_qa_logger_instance: Optional[QALogger] = None


def get_qa_logger(
    name: str = "qa_system",
    log_level: QALogLevel = QALogLevel.INFO,
    log_file: Optional[Union[str, Path]] = None,
    console_output: bool = True,
    structured: bool = True
) -> QALogger:
    """
    Get or create the global QA logger instance.
    
    Args:
        name: Logger name
        log_level: Minimum log level
        log_file: Optional file path for log output
        console_output: Whether to output to console
        structured: Whether to use JSON structured logging
        
    Returns:
        QALogger instance
    """
    global _qa_logger_instance
    
    if _qa_logger_instance is None:
        _qa_logger_instance = QALogger(
            name=name,
            log_level=log_level,
            log_file=log_file,
            console_output=console_output,
            structured=structured
        )
    
    return _qa_logger_instance


def reset_qa_logger() -> None:
    """Reset the global logger instance (useful for testing)"""
    global _qa_logger_instance
    _qa_logger_instance = None
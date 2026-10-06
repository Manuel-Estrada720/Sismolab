"""Section 8: FIFO queue of pending reports.

The order of the queue is the order of reception. The priority of an
earthquake decides its place in the AVL, never its place in the queue.
"""

from ..models.report import Report
from .report_processor import ReportProcessor


class QueueService:

    def __init__(self, state, processor=None):
        self.state = state
        self.processor = processor if processor is not None else ReportProcessor(state)

    @property
    def queue(self):
        return self.state.pending_reports

    def enqueue_burst(self, reports):
        """Add a burst of reports. All of them are checked first: if one is
        invalid, none is added."""
        if not reports:
            raise ValueError("La ráfaga debe tener al menos un reporte")
        for report in reports:
            if not isinstance(report, Report):
                raise TypeError("Cada elemento de la ráfaga debe ser un Report")
            if not self.state.has_station(report.station):
                raise ValueError("La estación " + report.station + " no existe en el escenario")
        for report in reports:
            self.queue.enqueue(report)
        return len(reports)

    def step(self):
        """Take the first report and resolve it completely.
        Returns (report, result, message)."""
        if self.queue.is_empty():
            raise ValueError("La cola de reportes está vacía")
        report = self.queue.dequeue()
        result, message = self.processor.process(report)
        return report, result, message

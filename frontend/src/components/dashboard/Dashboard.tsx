import { useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card';
import { useStore } from '../../stores/useStore';
import { apiClient } from '../../lib/api/client';
import { wsClient } from '../../lib/websocket/client';
import { CheckSquare, Activity, Clock, AlertCircle } from 'lucide-react';
import { Badge } from '../ui/Badge';

export function Dashboard() {
  const { systemStatus, tasks, runs, setSystemStatus, setTasks, setRuns, setWsConnected, loading, setLoading, error, setError } = useStore();

  useEffect(() => {
    loadDashboardData();

    // Setup WebSocket connection
    wsClient.connect();
    wsClient.on('connection:status', ({ connected }) => {
      setWsConnected(connected);
    });

    wsClient.on('task:update', () => {
      loadTasks();
    });

    wsClient.on('run:update', () => {
      loadRuns();
    });

    return () => {
      wsClient.disconnect();
    };
  }, []);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);

    try {
      // Load data in parallel
      const [status, tasksData, runsData] = await Promise.all([
        apiClient.getStatus(),
        apiClient.getTasks(),
        apiClient.getRuns(),
      ]);

      setSystemStatus(status);
      setTasks(tasksData.tasks);
      setRuns(runsData.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
      console.error('Error loading dashboard:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadTasks = async () => {
    try {
      const data = await apiClient.getTasks();
      setTasks(data.tasks);
    } catch (err) {
      console.error('Error loading tasks:', err);
    }
  };

  const loadRuns = async () => {
    try {
      const data = await apiClient.getRuns();
      setRuns(data.runs);
    } catch (error) {
      console.error('Error loading runs:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <Card className="max-w-md">
          <CardContent className="pt-6">
            <div className="flex items-center space-x-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <p className="font-semibold">Error loading dashboard</p>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{error}</p>
            <Button onClick={loadDashboardData} className="mt-4">
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const todoTasks = tasks.filter(t => t.status === 'todo').length;
  const inProgressTasks = tasks.filter(t => t.status === 'in_progress').length;
  const completedTasks = tasks.filter(t => t.status === 'done').length;
  const activeRuns = runs.filter(r => r.status === 'running' || r.status === 'started').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Welcome to Autoflow - Your AI Development Platform
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Tasks"
          value={tasks.length}
          icon={<CheckSquare className="h-5 w-5" />}
          color="text-blue-500"
        />
        <StatCard
          title="In Progress"
          value={inProgressTasks}
          icon={<Clock className="h-5 w-5" />}
          color="text-yellow-500"
        />
        <StatCard
          title="Completed"
          value={completedTasks}
          icon={<CheckSquare className="h-5 w-5" />}
          color="text-green-500"
        />
        <StatCard
          title="Active Runs"
          value={activeRuns}
          icon={<Activity className="h-5 w-5" />}
          color="text-purple-500"
        />
      </div>

      {/* Recent Tasks */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Tasks</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {tasks.slice(0, 5).map((task) => (
              <div
                key={task.id}
                className="flex items-center justify-between p-3 border rounded-lg hover:bg-accent/50 transition-colors"
              >
                <div className="flex-1">
                  <p className="font-medium text-foreground">{task.title}</p>
                  <p className="text-sm text-muted-foreground line-clamp-1">
                    {task.description}
                  </p>
                </div>
                <Badge
                  variant={
                    task.status === 'done'
                      ? 'success'
                      : task.status === 'in_progress'
                      ? 'info'
                      : task.status === 'blocked'
                      ? 'destructive'
                      : 'default'
                  }
                >
                  {task.status}
                </Badge>
              </div>
            ))}
            {tasks.length === 0 && (
              <p className="text-center text-muted-foreground py-8">
                No tasks yet. Create your first task to get started!
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* System Status */}
      {systemStatus && (
        <Card>
          <CardHeader>
            <CardTitle>System Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatusItem label="Status" value={systemStatus.status} />
              <StatusItem label="Version" value={systemStatus.version} />
              <StatusItem label="Tasks" value={systemStatus.tasks_total.toString()} />
              <StatusItem label="Runs" value={systemStatus.runs_total.toString()} />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({
  title,
  value,
  icon,
  color,
}: {
  title: string;
  value: number;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold text-foreground mt-1">{value}</p>
          </div>
          <div className={color}>{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="font-semibold text-foreground">{value}</p>
    </div>
  );
}

import { Button } from '../ui/Button';
import { useStore } from '../../stores/useStore';
import {
  LayoutDashboard,
  CheckSquare,
  Activity,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '../../utils/cn';

export function Sidebar() {
  const { sidebarOpen, toggleSidebar, currentView, setCurrentView } = useStore();

  const navigation = [
    { name: 'Dashboard', icon: LayoutDashboard, view: 'dashboard' as const },
    { name: 'Tasks', icon: CheckSquare, view: 'tasks' as const },
    { name: 'Runs', icon: Activity, view: 'runs' as const },
    { name: 'Settings', icon: Settings, view: 'settings' as const },
  ];

  return (
    <div
      className={cn(
        'flex flex-col bg-background border-r transition-all duration-300',
        sidebarOpen ? 'w-64' : 'w-16'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between h-16 px-4 border-b">
        {sidebarOpen && (
          <h1 className="text-xl font-bold text-foreground">Autoflow</h1>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleSidebar}
          className="ml-auto"
        >
          {sidebarOpen ? (
            <ChevronLeft className="h-5 w-5" />
          ) : (
            <ChevronRight className="h-5 w-5" />
          )}
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-1">
        {navigation.map((item) => {
          const Icon = item.icon;
          const isActive = currentView === item.view;

          return (
            <Button
              key={item.name}
              variant={isActive ? 'secondary' : 'ghost'}
              className={cn(
                'w-full justify-start',
                !sidebarOpen && 'px-2'
              )}
              onClick={() => setCurrentView(item.view)}
            >
              <Icon className="h-5 w-5" />
              {sidebarOpen && <span className="ml-2">{item.name}</span>}
            </Button>
          );
        })}
      </nav>

      {/* Connection Status */}
      <div className="p-4 border-t">
        <ConnectionIndicator />
      </div>
    </div>
  );
}

function ConnectionIndicator() {
  const { wsConnected } = useStore();

  return (
    <div className="flex items-center space-x-2">
      <div
        className={cn(
          'w-2 h-2 rounded-full',
          wsConnected ? 'bg-green-500' : 'bg-red-500'
        )}
      />
      {wsConnected ? (
        <span className="text-sm text-muted-foreground">Connected</span>
      ) : (
        <span className="text-sm text-muted-foreground">Disconnected</span>
      )}
    </div>
  );
}

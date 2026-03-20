import { useStore } from './stores/useStore';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { Dashboard } from './components/dashboard/Dashboard';

function App() {
  const { currentView } = useStore();

  const renderView = () => {
    switch (currentView) {
      case 'dashboard':
        return <Dashboard />;
      case 'tasks':
        return <div className="p-6">Tasks View - Coming Soon</div>;
      case 'runs':
        return <div className="p-6">Runs View - Coming Soon</div>;
      case 'settings':
        return <div className="p-6">Settings View - Coming Soon</div>;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          {renderView()}
        </main>
      </div>
    </div>
  );
}

export default App;

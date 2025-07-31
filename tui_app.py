#!/usr/bin/env python3
"""
GitKeeper - GitHub Repository Management Tool
Modern TUI interface for GitHub account backup and management.
"""

import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Button, DataTable, Static, Input, Log, 
    TabbedContent, TabPane, Tree, ProgressBar, Label, Switch,
    Select, RichLog
)
from textual.reactive import reactive
from textual.message import Message
from textual.binding import Binding
from textual.screen import Screen
from textual import events
from rich.text import Text
from rich.table import Table as RichTable
from rich.panel import Panel
from rich.progress import Progress

from github import Github, GithubException
from settings import SettingsManager
from github_backup import GitHubBackup


class SetupScreen(Screen):
    """Initial setup screen for configuring GitHub token and settings."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save Settings"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("🚀 GitHub Tools Setup", classes="title"),
            Static("Configure your GitHub token and default settings", classes="subtitle"),
            
            Container(
                Label("GitHub Personal Access Token:"),
                Input(placeholder="ghp_xxxxxxxxxxxxxxxxxxxx", password=True, id="token_input"),
                
                Label("Default Backup Directory:"),
                Input(value="./backups", id="backup_dir_input"),
                
                Label("Parallel Workers:"),
                Select([("1", 1), ("2", 2), ("4", 4), ("8", 8)], value=4, id="workers_select"),
                
                Horizontal(
                    Button("Save & Continue", variant="primary", id="save_btn"),
                    Button("Cancel", variant="default", id="cancel_btn"),
                    classes="buttons"
                ),
                classes="setup_form"
            ),
            classes="setup_container"
        )
        yield Footer()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self.action_save()
        elif event.button.id == "cancel_btn":
            self.action_cancel()
    
    def action_save(self) -> None:
        """Save settings and proceed to main app."""
        token_input = self.query_one("#token_input", Input)
        backup_dir_input = self.query_one("#backup_dir_input", Input)
        workers_select = self.query_one("#workers_select", Select)
        
        if not token_input.value:
            self.notify("Please enter your GitHub token", severity="error")
            return
            
        settings = SettingsManager()
        settings.set_github_token(token_input.value)
        settings.set_backup_directory(backup_dir_input.value)
        settings.set_parallel_workers(workers_select.value)
        
        self.notify("Settings saved successfully!", severity="information")
        self.app.push_screen("main")
    
    def action_cancel(self) -> None:
        """Cancel setup and exit."""
        self.app.exit()


class SelectiveBackupProgressScreen(Screen):
    """Screen showing real-time selective backup progress."""
    
    BINDINGS = [
        Binding("escape", "back", "Back to Dashboard"),
        Binding("ctrl+c", "cancel_backup", "Cancel Backup"),
    ]
    
    def __init__(self, backup_tool: GitHubBackup, selected_repos: set) -> None:
        super().__init__()
        self.backup_tool = backup_tool
        self.selected_repos = selected_repos
        self.backup_task = None
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(f"🔄 Selective Backup ({len(self.selected_repos)} repositories)", classes="title"),
            
            Container(
                Static("Overall Progress:", classes="section_title"),
                ProgressBar(total=100, id="overall_progress"),
                Label("Initializing...", id="overall_status"),
                
                Static("Repository Progress:", classes="section_title"),
                ProgressBar(total=100, id="repo_progress"),
                Label("Waiting...", id="repo_status"),
                
                Static("Current Operation:", classes="section_title"),
                Label("Starting selective backup...", id="current_operation"),
                
                classes="progress_container"
            ),
            
            Container(
                Static("Backup Log:", classes="section_title"),
                RichLog(id="backup_log", auto_scroll=True),
                classes="log_container"
            ),
            
            Horizontal(
                Button("Cancel Backup", variant="error", id="cancel_btn"),
                Button("Minimize", variant="default", id="minimize_btn"),
                classes="buttons"
            ),
            classes="backup_screen"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Start the selective backup process when screen loads."""
        self.backup_task = asyncio.create_task(self.run_selective_backup())
    
    async def run_selective_backup(self) -> None:
        """Run the selective backup process with progress updates."""
        log = self.query_one("#backup_log", RichLog)
        overall_progress = self.query_one("#overall_progress", ProgressBar)
        overall_status = self.query_one("#overall_status", Label)
        repo_progress = self.query_one("#repo_progress", ProgressBar)
        repo_status = self.query_one("#repo_status", Label)
        
        try:
            log.write(f"🚀 Starting selective backup of {len(self.selected_repos)} repositories...")
            overall_status.update("Initializing selective backup...")
            overall_progress.update(progress=10)
            
            # Run the actual selective backup process
            await asyncio.get_event_loop().run_in_executor(
                None, self._run_selective_backup_sync, log, overall_progress, overall_status, repo_progress, repo_status
            )
            
        except Exception as e:
            log.write(f"❌ Selective backup failed: {str(e)}")
            overall_status.update(f"Backup failed: {str(e)}")
    
    def _run_selective_backup_sync(self, log, overall_progress, overall_status, repo_progress, repo_status):
        """Run the synchronous selective backup process."""
        try:
            # Create backup structure
            log.write("📁 Creating backup directory structure...")
            overall_status.update("Creating backup structure...")
            overall_progress.update(progress=20)
            self.backup_tool.create_backup_structure()
            
            # Backup user information
            log.write("👤 Backing up user information...")
            overall_status.update("Backing up user information...")
            overall_progress.update(progress=30)
            self.backup_tool.backup_user_metadata()
            
            # Backup selected repositories only
            log.write(f"📦 Backing up {len(self.selected_repos)} selected repositories...")
            overall_status.update("Backing up selected repositories...")
            overall_progress.update(progress=40)
            
            # Call selective backup method
            self._backup_selected_repositories(log, repo_progress, repo_status)
            overall_progress.update(progress=85)
            
            # Skip gists for selective backup to keep it focused
            log.write("📝 Skipping gists in selective backup...")
            overall_status.update("Finalizing backup...")
            overall_progress.update(progress=95)
            
            log.write("✅ Selective backup completed successfully!")
            overall_status.update("Selective backup completed successfully!")
            overall_progress.update(progress=100)
            
            # Change Cancel button to Close button
            cancel_btn = self.query_one("#cancel_btn", Button)
            cancel_btn.label = "Close"
            cancel_btn.variant = "success"
            
        except Exception as e:
            log.write(f"❌ Selective backup failed: {str(e)}")
            overall_status.update(f"Backup failed: {str(e)}")
            raise
    
    def _backup_selected_repositories(self, log, repo_progress, repo_status):
        """Backup only the selected repositories."""
        # Get all repositories and filter by selected ones
        all_repos = self.backup_tool.get_all_repositories()
        selected_repo_objects = [repo for repo in all_repos if repo.name in self.selected_repos]
        
        clone_success = 0
        clone_failures = 0
        total_repos = len(selected_repo_objects)
        
        repo_progress.update(total=total_repos * 100)
        
        for i, repo in enumerate(selected_repo_objects):
            log.write(f"Processing repository: {repo.full_name}")
            repo_status.update(f"Backing up {repo.full_name}")
            
            repo_dir = self.backup_tool.backup_root / 'repositories' / repo.name
            repo_dir.mkdir(exist_ok=True)
            
            # Clone repository
            if self.backup_tool.clone_repository(repo, repo_dir / 'git'):
                log.write(f"✓ Cloned {repo.full_name}")
                clone_success += 1
            else:
                log.write(f"✗ Failed to clone {repo.full_name}")
                clone_failures += 1
                
            # Backup metadata
            log.write(f"Backing up metadata for {repo.full_name}")
            self.backup_tool.backup_repository_metadata(repo, repo_dir)
            
            # Update progress
            progress_value = ((i + 1) / total_repos) * 100
            repo_progress.update(progress=progress_value)
        
        log.write(f"Repository backup completed: {clone_success} successful, {clone_failures} failed")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            # Check if button has been changed to "Close"
            if event.button.label == "Close":
                self.action_back()
            else:
                self.action_cancel_backup()
        elif event.button.id == "minimize_btn":
            self.action_back()
    
    def action_cancel_backup(self) -> None:
        """Cancel the running backup."""
        if self.backup_task:
            self.backup_task.cancel()
        self.notify("Selective backup cancelled", severity="warning")
        self.action_back()
    
    def action_back(self) -> None:
        """Return to main dashboard."""
        self.app.pop_screen()


class BackupProgressScreen(Screen):
    """Screen showing real-time backup progress."""
    
    BINDINGS = [
        Binding("escape", "back", "Back to Dashboard"),
        Binding("ctrl+c", "cancel_backup", "Cancel Backup"),
    ]
    
    def __init__(self, backup_tool: GitHubBackup) -> None:
        super().__init__()
        self.backup_tool = backup_tool
        self.backup_task = None
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("🔄 GitHub Account Backup in Progress", classes="title"),
            
            Container(
                Static("Overall Progress:", classes="section_title"),
                ProgressBar(total=100, id="overall_progress"),
                Label("Initializing...", id="overall_status"),
                
                Static("Repository Progress:", classes="section_title"),
                ProgressBar(total=100, id="repo_progress"),
                Label("Waiting...", id="repo_status"),
                
                Static("Current Operation:", classes="section_title"),
                Label("Starting backup...", id="current_operation"),
                
                classes="progress_container"
            ),
            
            Container(
                Static("Backup Log:", classes="section_title"),
                RichLog(id="backup_log", auto_scroll=True),
                classes="log_container"
            ),
            
            Horizontal(
                Button("Cancel Backup", variant="error", id="cancel_btn"),
                Button("Minimize", variant="default", id="minimize_btn"),
                classes="buttons"
            ),
            classes="backup_screen"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Start the backup process when screen loads."""
        self.backup_task = asyncio.create_task(self.run_backup())
    
    async def run_backup(self) -> None:
        """Run the backup process with progress updates."""
        log = self.query_one("#backup_log", RichLog)
        overall_progress = self.query_one("#overall_progress", ProgressBar)
        overall_status = self.query_one("#overall_status", Label)
        
        try:
            log.write("🚀 Starting GitHub account backup...")
            overall_status.update("Initializing backup...")
            overall_progress.update(progress=10)
            
            # Run the actual backup process
            await asyncio.get_event_loop().run_in_executor(
                None, self._run_backup_sync, log, overall_progress, overall_status
            )
            
        except Exception as e:
            log.write(f"❌ Backup failed: {str(e)}")
            overall_status.update(f"Backup failed: {str(e)}")
    
    def _run_backup_sync(self, log, overall_progress, overall_status):
        """Run the synchronous backup process."""
        try:
            # Create backup structure
            log.write("📁 Creating backup directory structure...")
            overall_status.update("Creating backup structure...")
            overall_progress.update(progress=20)
            self.backup_tool.create_backup_structure()
            
            # Backup user information
            log.write("👤 Backing up user information...")
            overall_status.update("Backing up user information...")
            overall_progress.update(progress=30)
            self.backup_tool.backup_user_metadata()
            
            # Backup all repositories
            log.write("📦 Backing up repositories...")
            overall_status.update("Backing up repositories...")
            overall_progress.update(progress=40)
            self.backup_tool.backup_repositories()
            overall_progress.update(progress=85)
            
            # Backup gists
            log.write("📝 Backing up gists...")
            overall_status.update("Backing up gists...")
            overall_progress.update(progress=95)
            self.backup_tool.backup_gists()
            
            log.write("✅ Backup completed successfully!")
            overall_status.update("Backup completed successfully!")
            overall_progress.update(progress=100)
            
            # Change Cancel button to Close button
            cancel_btn = self.query_one("#cancel_btn", Button)
            cancel_btn.label = "Close"
            cancel_btn.variant = "success"
            
        except Exception as e:
            log.write(f"❌ Backup failed: {str(e)}")
            overall_status.update(f"Backup failed: {str(e)}")
            raise
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            # Check if button has been changed to "Close"
            if event.button.label == "Close":
                self.action_back()
            else:
                self.action_cancel_backup()
        elif event.button.id == "minimize_btn":
            self.action_back()
    
    def action_cancel_backup(self) -> None:
        """Cancel the running backup."""
        if self.backup_task:
            self.backup_task.cancel()
        self.notify("Backup cancelled", severity="warning")
        self.action_back()
    
    def action_back(self) -> None:
        """Return to main dashboard."""
        self.app.pop_screen()


class SettingsScreen(Screen):
    """Settings management screen."""
    
    BINDINGS = [
        Binding("escape", "back", "Back to Dashboard"),
        Binding("ctrl+s", "save", "Save Settings"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("⚙️  GitKeeper Settings", classes="title")
            
            with TabbedContent():
                with TabPane("General", id="general_tab"):
                    yield Container(
                        Label("GitHub Token:"),
                        Horizontal(
                            Input(placeholder="Token is encrypted and stored securely", 
                                 password=True, id="token_input"),
                            Button("Update Token", id="update_token_btn"),
                        ),
                        
                        Label("Default Backup Directory:"),
                        Horizontal(
                            Input(id="backup_dir_input"),
                            Button("Browse", id="browse_btn"),
                        ),
                        
                        Label("Parallel Workers:"),
                        Select([("1", 1), ("2", 2), ("4", 4), ("8", 8)], id="workers_select"),
                        
                        Label("Auto-backup Schedule:"),
                        Select([
                            ("Disabled", "disabled"),
                            ("Daily", "daily"), 
                            ("Weekly", "weekly"),
                            ("Monthly", "monthly")
                        ], value="disabled", id="schedule_select"),
                        
                        classes="settings_form"
                    )
                
                with TabPane("Advanced", id="advanced_tab"):
                    yield Container(
                        Label("GitHub API Settings:"),
                        
                        Horizontal(
                            Label("API Rate Limit Buffer:"),
                            Input(value="100", id="rate_limit_input"),
                        ),
                        
                        Horizontal(
                            Label("Request Timeout (seconds):"),
                            Input(value="30", id="timeout_input"),
                        ),
                        
                        Label("Backup Options:"),
                        
                        Horizontal(
                            Switch(id="backup_issues_switch"),
                            Label("Backup Issues & PRs"),
                        ),
                        
                        Horizontal(
                            Switch(id="backup_wikis_switch"),
                            Label("Backup Wiki Pages"),
                        ),
                        
                        Horizontal(
                            Switch(id="backup_releases_switch"),
                            Label("Backup Releases & Assets"),
                        ),
                        
                        classes="settings_form"
                    )
                
                with TabPane("Storage", id="storage_tab"):
                    yield Container(
                        DataTable(id="settings_table"),
                        
                        Horizontal(
                            Button("Add Setting", variant="primary", id="add_setting_btn"),
                            Button("Delete Selected", variant="error", id="delete_setting_btn"),
                            Button("Export Config", variant="default", id="export_btn"),
                        ),
                        
                        classes="storage_tab"
                    )
            
            yield Horizontal(
                Button("Save Changes", variant="primary", id="save_btn"),
                Button("Reset to Defaults", variant="error", id="reset_btn"),
                Button("Back", variant="default", id="back_btn"),
                classes="buttons"
            )
        yield Footer()
    
    def on_mount(self) -> None:
        """Load current settings when screen mounts."""
        self.load_settings()
    
    def load_settings(self) -> None:
        """Load settings from database into form."""
        settings = SettingsManager()
        
        # Load into form fields
        backup_dir = self.query_one("#backup_dir_input", Input)
        backup_dir.value = settings.get_backup_directory()
        
        workers_select = self.query_one("#workers_select", Select)
        workers_select.value = settings.get_parallel_workers()
        
        # Load settings table
        table = self.query_one("#settings_table", DataTable)
        table.add_columns("Key", "Encrypted", "Description", "Updated")
        
        for key, info in settings.list_settings().items():
            encrypted = "✓" if info['encrypted'] else ""
            table.add_row(key, encrypted, info['description'] or "", info['updated_at'])
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self.action_save()
        elif event.button.id == "back_btn":
            self.action_back()
        elif event.button.id == "update_token_btn":
            self.update_token()
    
    def update_token(self) -> None:
        """Update GitHub token."""
        token_input = self.query_one("#token_input", Input)
        if token_input.value:
            settings = SettingsManager()
            settings.set_github_token(token_input.value)
            self.notify("GitHub token updated!", severity="information")
            token_input.value = ""
    
    def action_save(self) -> None:
        """Save all settings."""
        settings = SettingsManager()
        
        # Save form values
        backup_dir = self.query_one("#backup_dir_input", Input)
        settings.set_backup_directory(backup_dir.value)
        
        workers_select = self.query_one("#workers_select", Select)
        settings.set_parallel_workers(workers_select.value)
        
        self.notify("Settings saved!", severity="information")
    
    def action_back(self) -> None:
        """Return to main dashboard."""
        self.app.pop_screen()


class MainDashboard(Screen):
    """Main dashboard screen with overview and actions."""
    
    BINDINGS = [
        Binding("b", "start_backup", "Start Backup"),
        Binding("s", "open_settings", "Settings"),
        Binding("r", "refresh", "Refresh"),
        Binding("delete", "delete_selected_repo", "Delete Selected Repo"),
        Binding("ctrl+d", "delete_all_repos", "Delete All Repos"),
        Binding("space", "toggle_repo_selection", "Toggle Repo Selection"),
        Binding("ctrl+a", "select_all_repos", "Select All Repos"),
        Binding("q", "quit", "Quit"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("🛡️  GitKeeper", classes="title"),
            
            Horizontal(
                # Left panel - Account info
                Container(
                    Static("📊 Account Overview", classes="section_title"),
                    Static("", id="account_info", classes="info_panel"),
                    
                    Static("🔧 Quick Actions", classes="section_title"),
                    Container(
                        Button("🔄 Start Full Backup", variant="primary", id="backup_btn"),
                        Button("📋 View Last Backup", variant="default", id="last_backup_btn"),
                        Button("⚙️  Settings", variant="default", id="settings_btn"),
                        Button("📈 Backup History", variant="default", id="history_btn"),
                        classes="action_buttons"
                    ),
                    classes="left_panel"
                ),
                
                # Right panel - Repository list
                Vertical(
                    Static("📁 Repositories", classes="section_title"),
                    DataTable(id="repos_table"),
                    
                    Horizontal(
                        Button("Refresh", id="refresh_btn"),
                        Button("🗑️  Delete Selected", variant="error", id="delete_repo_btn"),
                        Button("Select All", id="select_all_btn"),
                        Button("Backup Selected", id="backup_selected_btn"),
                        classes="repo_buttons"
                    ),
                    classes="right_panel"
                ),
            ),
            
            # Status bar
            Container(
                Label("Ready", id="status_label"),
                classes="status_bar"
            ),
            classes="dashboard"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize dashboard when mounted."""
        self.load_account_info()
        self.load_repositories()
    
    def load_account_info(self) -> None:
        """Load GitHub account information."""
        try:
            settings = SettingsManager()
            token = settings.get_github_token()
            
            if not token:
                self.query_one("#account_info").update("⚠️  No GitHub token configured")
                return
                
            github = Github(token)
            user = github.get_user()
            
            # Get actual repo counts by fetching repositories
            repos = list(user.get_repos(type='all'))
            private_count = sum(1 for repo in repos if repo.private)
            public_count = sum(1 for repo in repos if not repo.private)
            
            info_text = f"""
👤 **{user.login}** ({user.name or 'No name'})
📧 {user.email or 'Email private'}
📁 {public_count} public repos
🔐 {private_count} private repos
👥 {user.followers} followers, {user.following} following
📅 Joined {user.created_at.strftime('%Y-%m-%d') if user.created_at else 'Unknown'}
            """
            
            self.query_one("#account_info").update(info_text.strip())
            
        except Exception as e:
            self.query_one("#account_info").update(f"❌ Error loading account: {str(e)}")
    
    def load_repositories(self) -> None:
        """Load repositories into the table."""
        try:
            settings = SettingsManager()
            token = settings.get_github_token()
            
            if not token:
                return
                
            github = Github(token)
            user = github.get_user()
            
            table = self.query_one("#repos_table", DataTable)
            
            # Clear existing data
            table.clear()
            
            # Add columns only if they don't exist
            if not table.columns:
                table.add_columns("✓", "Name", "Type", "Language", "Updated")
            
            # Initialize selected repos set if it doesn't exist
            if not hasattr(self, 'selected_repos'):
                self.selected_repos = set()
            
            repos = list(user.get_repos(type='all'))[:20]  # Limit for demo
            
            for repo in repos:
                # Show selection status
                selected = "✓" if repo.name in self.selected_repos else " "
                repo_type = "Private" if repo.private else "Public"
                language = repo.language or "N/A"
                updated = repo.updated_at.strftime('%Y-%m-%d') if repo.updated_at else "N/A"
                
                table.add_row(selected, repo.name, repo_type, language, updated)
                
        except Exception as e:
            self.notify(f"Error loading repositories: {str(e)}", severity="error")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "backup_btn":
            self.action_start_backup()
        elif event.button.id == "settings_btn":
            self.action_open_settings()
        elif event.button.id == "refresh_btn":
            self.action_refresh()
        elif event.button.id == "delete_repo_btn":
            self.action_delete_selected_repo()
        elif event.button.id == "select_all_btn":
            self.action_select_all_repos()
        elif event.button.id == "backup_selected_btn":
            self.action_backup_selected_repos()
        elif event.button.id == "last_backup_btn":
            self.action_view_last_backup()
        elif event.button.id == "history_btn":
            self.action_view_backup_history()
    
    def action_start_backup(self) -> None:
        """Start full backup process."""
        try:
            settings = SettingsManager()
            backup_tool = GitHubBackup(settings_manager=settings)
            self.app.install_screen(BackupProgressScreen(backup_tool), name="backup_progress")
            self.app.push_screen("backup_progress")
        except Exception as e:
            self.notify(f"Error starting backup: {str(e)}", severity="error")
    
    def action_open_settings(self) -> None:
        """Open settings screen."""
        self.app.push_screen("settings")
    
    def action_refresh(self) -> None:
        """Refresh dashboard data."""
        self.load_account_info()
        self.load_repositories()
        self.notify("Dashboard refreshed", severity="information")
    
    def action_view_last_backup(self) -> None:
        """View the last backup details."""
        try:
            settings = SettingsManager()
            backup_dir = Path(settings.get_backup_directory())
            
            if not backup_dir.exists():
                self.notify("No backup directory found", severity="warning")
                return
                
            # Find the most recent backup directory
            backup_dirs = [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("github_backup_")]
            
            if not backup_dirs:
                self.notify("No backups found", severity="information")
                return
                
            latest_backup = max(backup_dirs, key=lambda d: d.stat().st_mtime)
            
            # Show backup info screen
            if self.app.is_screen_installed("backup_view"):
                self.app.uninstall_screen("backup_view")
            
            self.app.install_screen(BackupViewScreen(latest_backup), name="backup_view")
            self.app.push_screen("backup_view")
            
        except Exception as e:
            self.notify(f"Error viewing backup: {str(e)}", severity="error")
    
    def action_view_backup_history(self) -> None:
        """View all backup history and allow selection."""
        try:
            settings = SettingsManager()
            backup_dir = Path(settings.get_backup_directory())
            
            if not backup_dir.exists():
                self.notify("No backup directory found", severity="warning")
                return
                
            # Find all backup directories
            backup_dirs = [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("github_backup_")]
            
            if not backup_dirs:
                self.notify("No backups found", severity="information")
                return
                
            # Sort by creation time (most recent first)
            backup_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            
            # Show backup history screen - uninstall if it exists first
            if self.app.is_screen_installed("backup_history"):
                self.app.uninstall_screen("backup_history")
            
            self.app.install_screen(BackupHistoryScreen(backup_dirs), name="backup_history")
            self.app.push_screen("backup_history")
            
        except Exception as e:
            self.notify(f"Error viewing backup history: {str(e)}", severity="error")
    
    def action_delete_selected_repo(self) -> None:
        """Delete the currently selected repository from GitHub."""
        try:
            table = self.query_one("#repos_table", DataTable)
            if table.cursor_row < 0 or table.cursor_row >= table.row_count:
                self.notify("No repository selected", severity="warning")
                return
            
            repo_name = table.get_row_at(table.cursor_row)[1]  # Name is now in column 1
            
            # Simple confirmation via notification for now
            self.pending_delete_repo = repo_name
            self.notify(f"⚠️  Press Ctrl+Y to confirm deletion of '{repo_name}' or any other key to cancel", severity="warning")
            self.awaiting_delete_confirmation = True
            
        except Exception as e:
            self.notify(f"Error selecting repository: {str(e)}", severity="error")
    
    def action_delete_all_repos(self) -> None:
        """Delete ALL repositories from GitHub with confirmation."""
        try:
            settings = SettingsManager()
            token = settings.get_github_token()
            if not token:
                self.notify("No GitHub token configured", severity="error")
                return
            
            from github import Github
            github = Github(token)
            user = github.get_user()
            repos = list(user.get_repos(type='all'))
            
            if not repos:
                self.notify("No repositories found to delete", severity="information")
                return
            
            # Show serious warning
            self.notify(f"🚨 WARNING: This will DELETE ALL {len(repos)} repositories from GitHub!", severity="error")
            self.notify(f"⚠️  Press Ctrl+Y to confirm DELETION OF ALL REPOS or any other key to cancel", severity="error")
            self.awaiting_delete_all_confirmation = True
            
        except Exception as e:
            self.notify(f"Error preparing to delete all repos: {str(e)}", severity="error")
    
    def on_key(self, event) -> None:
        """Handle key presses for confirmations."""
        if hasattr(self, 'awaiting_delete_confirmation') and self.awaiting_delete_confirmation:
            self.awaiting_delete_confirmation = False
            
            if event.key == "ctrl+y" and hasattr(self, 'pending_delete_repo'):
                self._execute_single_repo_delete(self.pending_delete_repo)
            else:
                self.notify("Repository deletion cancelled", severity="information")
            
            if hasattr(self, 'pending_delete_repo'):
                delattr(self, 'pending_delete_repo')
            return
        
        if hasattr(self, 'awaiting_delete_all_confirmation') and self.awaiting_delete_all_confirmation:
            self.awaiting_delete_all_confirmation = False
            
            if event.key == "ctrl+y":
                self._execute_delete_all_repos()
            else:
                self.notify("Delete all repositories cancelled", severity="information")
            return
        
        # Handle normal key bindings - let the app handle them
    
    def _execute_single_repo_delete(self, repo_name: str) -> None:
        """Execute the actual deletion of a single repository."""
        try:
            settings = SettingsManager()
            token = settings.get_github_token()
            
            from github import Github
            github = Github(token)
            user = github.get_user()
            
            repo = user.get_repo(repo_name)
            
            # Check if repo exists and get info before deletion
            repo_full_name = repo.full_name
            repo_private = repo.private
            
            self.notify(f"🔄 Deleting repository '{repo_full_name}'...", severity="information")
            
            # Delete the entire repository
            self.notify(f"📡 Making API call to delete '{repo_full_name}'...", severity="information")
            result = repo.delete()
            self.notify(f"✅ API call completed. Result: {result}", severity="information")
            
            # Add a small delay and double-check deletion
            import time
            time.sleep(1)
            
            try:
                # Try to access the repo again - should fail if truly deleted
                check_repo = user.get_repo(repo_name)
                self.notify(f"⚠️  Repository '{repo_full_name}' still exists after deletion attempt", severity="warning")
            except:
                # This is expected - repo should not be found after deletion
                self.notify(f"🗑️  Successfully deleted repository '{repo_full_name}'", severity="information")
            
            # Refresh the repository list
            self.load_repositories()
            
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg:
                self.notify(f"Repository '{repo_name}' not found (may already be deleted)", severity="warning")
            elif "forbidden" in error_msg:
                self.notify(f"❌ Permission denied: Token may lack 'delete_repo' scope", severity="error")
            elif "protected" in error_msg:
                self.notify(f"❌ Repository '{repo_name}' is protected from deletion", severity="error")
            else:
                self.notify(f"Error deleting repository '{repo_name}': {str(e)}", severity="error")
    
    def _execute_delete_all_repos(self) -> None:
        """Execute the actual deletion of all repositories."""
        try:
            settings = SettingsManager()
            token = settings.get_github_token()
            
            from github import Github
            github = Github(token)
            user = github.get_user()
            
            repos = list(user.get_repos(type='all'))
            deleted_count = 0
            failed_count = 0
            
            for repo in repos:
                try:
                    repo.delete()
                    deleted_count += 1
                    self.notify(f"🗑️  Deleted {repo.name} ({deleted_count}/{len(repos)})", severity="information")
                except Exception as e:
                    failed_count += 1
                    self.notify(f"❌ Failed to delete {repo.name}: {str(e)}", severity="error")
            
            if deleted_count > 0:
                self.notify(f"✅ Deleted {deleted_count} repositories", severity="information")
            
            if failed_count > 0:
                self.notify(f"⚠️  {failed_count} repositories failed to delete", severity="warning")
            
            # Refresh the repository list
            self.load_repositories()
            
        except Exception as e:
            self.notify(f"Error during bulk delete: {str(e)}", severity="error")
    
    def action_toggle_repo_selection(self) -> None:
        """Toggle selection of the currently highlighted repository."""
        try:
            table = self.query_one("#repos_table", DataTable)
            if table.cursor_row < 0 or table.cursor_row >= table.row_count:
                self.notify("No repository selected", severity="warning")
                return
            
            # Initialize selected repos set if it doesn't exist
            if not hasattr(self, 'selected_repos'):
                self.selected_repos = set()
            
            # Get repo name from the currently highlighted row (Name is in column 1)
            repo_name = table.get_row_at(table.cursor_row)[1]
            
            # Toggle selection
            if repo_name in self.selected_repos:
                self.selected_repos.remove(repo_name)
                action = "deselected"
            else:
                self.selected_repos.add(repo_name)
                action = "selected"
            
            # Refresh the table to update visual indicators
            self.load_repositories()
            
            self.notify(f"📋 {action.title()} '{repo_name}' ({len(self.selected_repos)} total selected)", severity="information")
            
        except Exception as e:
            self.notify(f"Error toggling selection: {str(e)}", severity="error")
    
    def action_select_all_repos(self) -> None:
        """Select all repositories in the table."""
        try:
            table = self.query_one("#repos_table", DataTable)
            if table.row_count == 0:
                self.notify("No repositories to select", severity="information")
                return
            
            # Initialize selected repos set if it doesn't exist
            if not hasattr(self, 'selected_repos'):
                self.selected_repos = set()
            
            # Check if all repos are already selected
            all_repo_names = set()
            for row_index in range(table.row_count):
                repo_name = table.get_row_at(row_index)[1]  # Name is in column 1
                all_repo_names.add(repo_name)
            
            if all_repo_names.issubset(self.selected_repos):
                # All are selected, so deselect all
                self.selected_repos -= all_repo_names
                action = "Deselected all"
            else:
                # Not all are selected, so select all
                self.selected_repos.update(all_repo_names)
                action = "Selected all"
            
            # Refresh the table to update visual indicators
            self.load_repositories()
            
            self.notify(f"📋 {action} repositories ({len(self.selected_repos)} total selected)", severity="information")
            
        except Exception as e:
            self.notify(f"Error selecting all repos: {str(e)}", severity="error")
    
    def action_backup_selected_repos(self) -> None:
        """Backup only the selected repositories."""
        try:
            if not hasattr(self, 'selected_repos') or not self.selected_repos:
                self.notify("No repositories selected. Use spacebar to select individual repos or Ctrl+A to select all.", severity="warning")
                return
            
            selected_count = len(self.selected_repos)
            
            # Create a custom backup tool for selected repositories
            settings = SettingsManager()
            backup_tool = GitHubBackup(settings_manager=settings)
            
            # Create a custom backup screen for selected repos
            self.app.install_screen(SelectiveBackupProgressScreen(backup_tool, self.selected_repos), name="selective_backup_progress")
            self.app.push_screen("selective_backup_progress")
            
        except Exception as e:
            self.notify(f"Error backing up selected repos: {str(e)}", severity="error")


class BackupHistoryScreen(Screen):
    """Screen to view backup history and select a backup to view."""
    
    BINDINGS = [
        Binding("escape", "back", "Back to Dashboard"),
        Binding("enter", "view_selected", "View Selected Backup"),
        Binding("delete", "delete_selected", "Delete Selected Backup"),
    ]
    
    def __init__(self, backup_dirs: List[Path]) -> None:
        super().__init__()
        self.backup_dirs = backup_dirs
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("📈 GitKeeper Backup History", classes="title"),
            
            Container(
                Static("📊 Available Backups", classes="section_title"),
                DataTable(id="backups_table"),
                classes="table_section"
            ),
            
            Horizontal(
                Button("🔍 View Selected", variant="primary", id="view_btn"),
                Button("🗑️  Delete Selected", variant="error", id="delete_btn"),
                Button("🔄 Refresh", variant="default", id="refresh_btn"),
                Button("Back", variant="default", id="back_btn"),
                classes="buttons"
            ),
            classes="backup_history_screen"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Load backup history when screen mounts."""
        self.load_backup_history()
    
    def load_backup_history(self) -> None:
        """Load backup history into the table."""
        try:
            table = self.query_one("#backups_table", DataTable)
            table.clear()
            table.add_columns("Date & Time", "Size", "Repositories", "Type", "Age")
            
            for backup_dir in self.backup_dirs:
                try:
                    # Parse backup name to get date/time
                    backup_name = backup_dir.name
                    # Extract timestamp from name like: github_backup_Viroscope_20250731_140538
                    parts = backup_name.split('_')
                    if len(parts) >= 4:
                        date_str = parts[-2]  # 20250731
                        time_str = parts[-1]  # 140538
                        # Format: YYYY-MM-DD HH:MM:SS
                        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                    else:
                        formatted_date = "Unknown"
                    
                    # Get backup size
                    total_size = sum(f.stat().st_size for f in backup_dir.rglob('*') if f.is_file())
                    size_mb = total_size / (1024 * 1024)
                    size_text = f"{size_mb:.1f} MB"
                    
                    # Count repositories
                    repos_dir = backup_dir / 'repositories'
                    repo_count = len(list(repos_dir.iterdir())) if repos_dir.exists() else 0
                    
                    # Determine backup type
                    backup_type = "Full"  # Could be enhanced to detect selective backups
                    
                    # Calculate age
                    age_seconds = time.time() - backup_dir.stat().st_mtime
                    if age_seconds < 3600:  # Less than 1 hour
                        age = f"{int(age_seconds // 60)} min ago"
                    elif age_seconds < 86400:  # Less than 1 day
                        age = f"{int(age_seconds // 3600)} hrs ago"
                    else:  # Days
                        age = f"{int(age_seconds // 86400)} days ago"
                    
                    table.add_row(formatted_date, size_text, str(repo_count), backup_type, age)
                    
                except Exception as e:
                    # Add row with error info if we can't parse this backup
                    table.add_row(backup_dir.name, "Error", "?", "Unknown", f"Error: {str(e)[:20]}")
                    
        except Exception as e:
            self.notify(f"Error loading backup history: {str(e)}", severity="error")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back_btn":
            self.action_back()
        elif event.button.id == "view_btn":
            self.action_view_selected()
        elif event.button.id == "delete_btn":
            self.action_delete_selected()
        elif event.button.id == "refresh_btn":
            self.action_refresh()
    
    def on_data_table_row_selected(self, event) -> None:
        """Handle row selection in the backups table."""
        table = event.data_table
        if table.cursor_row >= 0 and table.cursor_row < table.row_count:
            # Store the selected backup index
            self.selected_backup_index = table.cursor_row
    
    def action_view_selected(self) -> None:
        """View the selected backup."""
        try:
            table = self.query_one("#backups_table", DataTable)
            if table.cursor_row < 0 or table.cursor_row >= table.row_count:
                self.notify("No backup selected", severity="warning")
                return
            
            # Get the selected backup directory
            selected_backup = self.backup_dirs[table.cursor_row]
            
            # Open the backup view screen with the selected backup
            if self.app.is_screen_installed("backup_view"):
                self.app.uninstall_screen("backup_view")
            
            self.app.install_screen(BackupViewScreen(selected_backup), name="backup_view")
            self.app.push_screen("backup_view")
            
        except Exception as e:
            self.notify(f"Error viewing selected backup: {str(e)}", severity="error")
    
    def action_delete_selected(self) -> None:
        """Delete the selected backup."""
        try:
            table = self.query_one("#backups_table", DataTable)
            if table.cursor_row < 0 or table.cursor_row >= table.row_count:
                self.notify("No backup selected", severity="warning")
                return
            
            selected_backup = self.backup_dirs[table.cursor_row]
            backup_name = selected_backup.name
            
            # Simple confirmation for now
            self.pending_delete_backup = selected_backup
            self.pending_delete_index = table.cursor_row
            self.notify(f"⚠️  Press Ctrl+Y to confirm deletion of backup '{backup_name}' or any other key to cancel", severity="warning")
            self.awaiting_delete_backup_confirmation = True
            
        except Exception as e:
            self.notify(f"Error selecting backup for deletion: {str(e)}", severity="error")
    
    def action_refresh(self) -> None:
        """Refresh the backup history."""
        # Reload backup directories
        try:
            settings = SettingsManager()
            backup_dir = Path(settings.get_backup_directory())
            
            if backup_dir.exists():
                backup_dirs = [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("github_backup_")]
                backup_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                self.backup_dirs = backup_dirs
                
            self.load_backup_history()
            self.notify("Backup history refreshed", severity="information")
            
        except Exception as e:
            self.notify(f"Error refreshing backup history: {str(e)}", severity="error")
    
    def on_key(self, event) -> None:
        """Handle key presses for backup deletion confirmation."""
        if hasattr(self, 'awaiting_delete_backup_confirmation') and self.awaiting_delete_backup_confirmation:
            self.awaiting_delete_backup_confirmation = False
            
            if event.key == "ctrl+y" and hasattr(self, 'pending_delete_backup'):
                self._execute_backup_deletion()
            else:
                self.notify("Backup deletion cancelled", severity="information")
            
            # Clean up
            if hasattr(self, 'pending_delete_backup'):
                delattr(self, 'pending_delete_backup')
            if hasattr(self, 'pending_delete_index'):
                delattr(self, 'pending_delete_index')
            return
    
    def _execute_backup_deletion(self) -> None:
        """Execute the actual backup deletion."""
        try:
            import shutil
            
            backup_to_delete = self.pending_delete_backup
            backup_name = backup_to_delete.name
            
            self.notify(f"🔄 Deleting backup '{backup_name}'...", severity="information")
            
            # Delete the entire backup directory
            shutil.rmtree(backup_to_delete)
            
            # Remove from our list
            self.backup_dirs.remove(backup_to_delete)
            
            # Refresh the table
            self.load_backup_history()
            
            self.notify(f"🗑️  Successfully deleted backup '{backup_name}'", severity="information")
            
        except Exception as e:
            self.notify(f"Error deleting backup: {str(e)}", severity="error")
    
    def action_back(self) -> None:
        """Return to main dashboard."""
        self.app.pop_screen()


class BackupViewScreen(Screen):
    """Screen to view backup details and contents."""
    
    BINDINGS = [
        Binding("escape", "back", "Back to Dashboard"),
        Binding("enter", "extract_selected", "Extract Selected Repo"),
        Binding("delete", "delete_selected", "Delete Selected Repo"),
        Binding("ctrl+a", "extract_all", "Extract All Repos"),
    ]
    
    def __init__(self, backup_path: Path) -> None:
        super().__init__()
        self.backup_path = backup_path
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(f"📁 Backup Details: {self.backup_path.name}", classes="title"),
            
            Container(
                Static("📊 Backup Overview", classes="section_title"),
                Static("", id="backup_info", classes="info_panel"),
                classes="info_section"
            ),
            
            Container(
                Static("📦 Repository Contents", classes="section_title"),
                DataTable(id="repos_table"),
                classes="table_section"
            ),
            
            Horizontal(
                Button("🚀 Open Backup Folder", variant="primary", id="open_folder_btn"),
                Button("📁 Extract All Repos", variant="default", id="extract_all_btn"),
                Button("🗑️  Delete Backup", variant="error", id="delete_backup_btn"),
                Button("Back", variant="default", id="back_btn"),
                classes="buttons"
            ),
            classes="backup_view_screen"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Load backup information when screen mounts."""
        self.load_backup_info()
        self.load_backup_contents()
    
    def load_backup_info(self) -> None:
        """Load and display backup information."""
        try:
            # Get backup creation time
            created = datetime.fromtimestamp(self.backup_path.stat().st_mtime)
            
            # Get backup size
            total_size = sum(f.stat().st_size for f in self.backup_path.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            
            # Count repositories
            repos_dir = self.backup_path / 'repositories'
            repo_count = len(list(repos_dir.iterdir())) if repos_dir.exists() else 0
            
            info_text = f"""
📅 Created: {created.strftime('%Y-%m-%d %H:%M:%S')}
💾 Size: {size_mb:.1f} MB
📦 Repositories: {repo_count}
📁 Location: {self.backup_path}
            """
            
            self.query_one("#backup_info").update(info_text.strip())
            
        except Exception as e:
            self.query_one("#backup_info").update(f"❌ Error loading backup info: {str(e)}")
    
    def load_backup_contents(self) -> None:
        """Load backup contents into the table."""
        try:
            table = self.query_one("#repos_table", DataTable)
            table.add_columns("Repository", "Type", "Size", "Status")
            
            repos_dir = self.backup_path / 'repositories'
            if not repos_dir.exists():
                return
                
            for repo_dir in repos_dir.iterdir():
                if repo_dir.is_dir():
                    # Check if git repo was cloned (bare repository)
                    git_dir = repo_dir / 'git'
                    has_git = git_dir.exists() and (git_dir / 'HEAD').exists() and (git_dir / 'objects').exists()
                    
                    # Calculate size
                    size = sum(f.stat().st_size for f in repo_dir.rglob('*') if f.is_file())
                    size_mb = size / (1024 * 1024)
                    
                    # Check for metadata
                    metadata_file = repo_dir / 'metadata.json'
                    has_metadata = metadata_file.exists()
                    
                    status = "✅ Complete" if (has_git and has_metadata) else "⚠️ Partial"
                    repo_type = "Bare Git + Metadata" if (has_git and has_metadata) else "Metadata Only" if has_metadata else "Unknown"
                    
                    table.add_row(repo_dir.name, repo_type, f"{size_mb:.1f} MB", status)
                    
        except Exception as e:
            self.notify(f"Error loading backup contents: {str(e)}", severity="error")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back_btn":
            self.action_back()
        elif event.button.id == "open_folder_btn":
            self.action_open_folder()
        elif event.button.id == "extract_all_btn":
            self.action_extract_all_repos()
        elif event.button.id == "delete_backup_btn":
            self.action_delete_backup()
    
    def on_data_table_row_selected(self, event) -> None:
        """Handle row selection in the repos table."""
        table = event.data_table
        if table.cursor_row >= 0 and table.cursor_row < table.row_count:
            # Get the selected repository name
            self.selected_repo = table.get_row_at(table.cursor_row)[0]
    
    def on_data_table_cell_selected(self, event) -> None:
        """Handle cell selection to track selected repo."""
        if event.coordinate.row >= 0:
            table = event.data_table
            self.selected_repo = table.get_row_at(event.coordinate.row)[0]
    
    def on_data_table_cell_highlighted(self, event) -> None:
        """Handle double-click on table cell to show context menu."""
        if event.coordinate.row >= 0:
            table = event.data_table
            repo_name = table.get_row_at(event.coordinate.row)[0]
            self.show_repo_context_menu(repo_name)
    
    def action_open_folder(self) -> None:
        """Open backup folder in system file manager."""
        import subprocess
        import platform
        
        try:
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["open", str(self.backup_path)])
            elif system == "Windows":
                subprocess.run(["explorer", str(self.backup_path)])
            else:  # Linux
                subprocess.run(["xdg-open", str(self.backup_path)])
            
            self.notify("Opened backup folder", severity="information")
        except Exception as e:
            self.notify(f"Error opening folder: {str(e)}", severity="error")
    
    def action_extract_single_repo(self, repo_name: str) -> None:
        """Extract a single repository to working directory."""
        try:
            import subprocess
            
            # Create extracted repos directory
            extract_dir = self.backup_path / 'extracted_repos'
            extract_dir.mkdir(exist_ok=True)
            
            repo_backup_dir = self.backup_path / 'repositories' / repo_name
            git_dir = repo_backup_dir / 'git'
            
            if not git_dir.exists():
                self.notify(f"No git backup found for {repo_name}", severity="error")
                return
            
            # Extract to working directory
            extract_repo_dir = extract_dir / repo_name
            
            # Remove existing extraction
            if extract_repo_dir.exists():
                import shutil
                shutil.rmtree(extract_repo_dir)
            
            # Clone from bare repo to working directory
            subprocess.run([
                'git', 'clone', str(git_dir), str(extract_repo_dir)
            ], check=True, capture_output=True)
            
            self.notify(f"✅ Extracted {repo_name} to {extract_repo_dir}", severity="information")
            
        except subprocess.CalledProcessError as e:
            self.notify(f"Failed to extract {repo_name}: {e.stderr.decode()}", severity="error")
        except Exception as e:
            self.notify(f"Error extracting {repo_name}: {str(e)}", severity="error")
    
    def action_extract_all_repos(self) -> None:
        """Extract all repositories to working directories."""
        try:
            repos_dir = self.backup_path / 'repositories'
            if not repos_dir.exists():
                self.notify("No repositories found in backup", severity="warning")
                return
            
            extracted_count = 0
            failed_count = 0
            
            for repo_dir in repos_dir.iterdir():
                if repo_dir.is_dir():
                    git_dir = repo_dir / 'git'
                    if git_dir.exists() and (git_dir / 'HEAD').exists():
                        try:
                            self.action_extract_single_repo(repo_dir.name)
                            extracted_count += 1
                        except:
                            failed_count += 1
            
            if extracted_count > 0:
                extract_dir = self.backup_path / 'extracted_repos'
                self.notify(f"✅ Extracted {extracted_count} repos to {extract_dir}", severity="information")
            
            if failed_count > 0:
                self.notify(f"⚠️  {failed_count} repos failed to extract", severity="warning")
                
        except Exception as e:
            self.notify(f"Error extracting repos: {str(e)}", severity="error")
    
    def action_delete_backup(self) -> None:
        """Delete the backup after confirmation."""
        # For now, just show a warning - would implement confirmation dialog
        self.notify("⚠️  Delete would remove entire backup - feature disabled for safety", severity="warning")
    
    def action_extract_selected(self) -> None:
        """Extract the currently selected repository."""
        if hasattr(self, 'selected_repo') and self.selected_repo:
            self.action_extract_single_repo(self.selected_repo)
        else:
            self.notify("No repository selected", severity="warning")
    
    def action_delete_selected(self) -> None:
        """Delete the currently selected repository."""
        if hasattr(self, 'selected_repo') and self.selected_repo:
            self.action_delete_single_repo(self.selected_repo)
        else:
            self.notify("No repository selected", severity="warning")
    
    def action_extract_all(self) -> None:
        """Extract all repositories (same as extract_all_repos)."""
        self.action_extract_all_repos()
    
    def action_delete_single_repo(self, repo_name: str) -> None:
        """Delete a single repository from the backup."""
        try:
            import shutil
            
            repo_backup_dir = self.backup_path / 'repositories' / repo_name
            if repo_backup_dir.exists():
                shutil.rmtree(repo_backup_dir)
                self.notify(f"🗑️  Deleted {repo_name} from backup", severity="information")
                
                # Refresh the table to show the change
                self.load_backup_contents()
            else:
                self.notify(f"Repository {repo_name} not found", severity="error")
                
        except Exception as e:
            self.notify(f"Error deleting {repo_name}: {str(e)}", severity="error")
    
    def show_repo_context_menu(self, repo_name: str) -> None:
        """Show context menu for repository actions."""
        from textual.widgets import OptionList
        from textual.containers import Center
        
        # Create a simple action selection using notifications for now
        # In a full implementation, this would be a proper modal dialog
        actions = [
            ("📁 Extract to Working Directory", "extract"),
            ("🔍 View Repository Details", "details"), 
            ("🗑️  Delete from Backup", "delete"),
            ("❌ Cancel", "cancel")
        ]
        
        # For now, show options in notifications - would be better as a modal
        action_text = f"\n🎯 Actions for '{repo_name}':\n"
        action_text += "Press 'E' to Extract, 'R' to Restore, 'D' to Delete, 'I' for Info"
        
        self.selected_repo = repo_name
        self.notify(action_text, severity="information")
        
        # Set a flag to handle next keypress
        self.awaiting_action = True
    
    def on_key(self, event) -> None:
        """Handle key presses for context menu actions."""
        if hasattr(self, 'awaiting_restore_choice') and self.awaiting_restore_choice:
            self.awaiting_restore_choice = False
            
            if event.key.lower() == 'o':  # Original privacy setting
                self._execute_restore_with_privacy(self.restore_original_private)
            elif event.key.lower() == 'p':  # Public
                self._execute_restore_with_privacy(False)
            elif event.key.lower() == 'r':  # Private
                self._execute_restore_with_privacy(True)
            elif event.key == 'escape':
                self.notify("Repository restore cancelled", severity="information")
            else:
                self.notify("Invalid choice. Repository restore cancelled.", severity="warning")
            
            # Clean up restore state variables
            for attr in ['restore_repo_name', 'restore_original_private', 'restore_original_description', 
                        'restore_github', 'restore_user', 'restore_repo_backup_dir']:
                if hasattr(self, attr):
                    delattr(self, attr)
            
            event.prevent_default()
            return
        
        if hasattr(self, 'awaiting_action') and self.awaiting_action:
            self.awaiting_action = False
            
            if event.key.lower() == 'e' and hasattr(self, 'selected_repo'):
                self.action_extract_single_repo(self.selected_repo)
            elif event.key.lower() == 'r' and hasattr(self, 'selected_repo'):
                self.action_restore_single_repo(self.selected_repo)
            elif event.key.lower() == 'd' and hasattr(self, 'selected_repo'):
                self.action_delete_single_repo(self.selected_repo)
            elif event.key.lower() == 'i' and hasattr(self, 'selected_repo'):
                self.show_repo_details(self.selected_repo)
            
            event.prevent_default()
            return
            
        # Handle normal key bindings if not in context menu mode - let the app handle them
    
    def show_repo_details(self, repo_name: str) -> None:
        """Show detailed information about a repository."""
        try:
            repo_dir = self.backup_path / 'repositories' / repo_name
            git_dir = repo_dir / 'git'
            metadata_file = repo_dir / 'metadata.json'
            
            details = f"📊 Repository: {repo_name}\n"
            
            if git_dir.exists():
                # Get repository size
                size = sum(f.stat().st_size for f in repo_dir.rglob('*') if f.is_file())
                details += f"💾 Size: {size / (1024 * 1024):.1f} MB\n"
                
                # Get commit count (if possible)
                try:
                    import subprocess
                    result = subprocess.run(
                        ['git', '--git-dir', str(git_dir), 'rev-list', '--count', 'HEAD'],
                        capture_output=True, text=True, check=True
                    )
                    commit_count = result.stdout.strip()
                    details += f"📝 Commits: {commit_count}\n"
                except:
                    details += "📝 Commits: Unable to count\n"
            
            if metadata_file.exists():
                details += "📋 Metadata: Available\n"
            
            details += f"📁 Location: {repo_dir}"
            
            self.notify(details, severity="information")
            
        except Exception as e:
            self.notify(f"Error getting details for {repo_name}: {str(e)}", severity="error")
    
    def action_restore_single_repo(self, repo_name: str) -> None:
        """Restore a repository from backup to GitHub."""
        try:
            from settings import SettingsManager
            from github import Github
            import subprocess
            import tempfile
            
            # Get GitHub token
            settings = SettingsManager()
            token = settings.get_github_token()
            if not token:
                self.notify("No GitHub token configured", severity="error")
                return
            
            github = Github(token)
            user = github.get_user()
            
            # Check if repo already exists on GitHub
            try:
                existing_repo = user.get_repo(repo_name)
                self.notify(f"⚠️  Repository {repo_name} already exists on GitHub", severity="warning")
                return
            except:
                pass  # Repo doesn't exist, which is what we want
            
            # Read original repository metadata to get privacy and other settings
            repo_backup_dir = self.backup_path / 'repositories' / repo_name
            metadata_file = repo_backup_dir / 'metadata.json'
            
            original_private = False  # Default to public if no metadata
            original_description = None
            
            if metadata_file.exists():
                try:
                    import json
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        original_private = metadata.get('private', False)
                        original_description = metadata.get('description', '')
                        
                    privacy_text = "private" if original_private else "public"
                    self.notify(f"📋 Original repository was {privacy_text}", severity="information")
                except Exception as e:
                    self.notify(f"⚠️  Could not read original metadata: {e}", severity="warning")
            
            # Prompt user for privacy choice
            self.restore_repo_name = repo_name
            self.restore_original_private = original_private
            self.restore_original_description = original_description
            self.restore_github = github
            self.restore_user = user
            self.restore_repo_backup_dir = repo_backup_dir
            
            privacy_choice = "private" if original_private else "public"
            self.notify(f"🔧 Restore Options for '{repo_name}' (originally {privacy_choice}):", severity="information")
            self.notify("Press 'O' for Original, 'P' for Public, 'R' for Private, ESC to cancel", severity="information")
            self.awaiting_restore_choice = True
            return  # Wait for user input
            
        except subprocess.CalledProcessError as e:
            self.notify(f"Git error restoring {repo_name}: {e.stderr.decode()}", severity="error")
        except Exception as e:
            self.notify(f"Error restoring {repo_name}: {str(e)}", severity="error")
    
    def _execute_restore_with_privacy(self, make_private: bool) -> None:
        """Execute the actual repository restore with specified privacy setting."""
        try:
            import subprocess
            import tempfile
            
            repo_name = self.restore_repo_name
            user = self.restore_user
            original_description = self.restore_original_description
            
            # Create new repository on GitHub with chosen privacy setting
            privacy_text = "private" if make_private else "public"
            self.notify(f"🔄 Creating {privacy_text} repository {repo_name} on GitHub...", severity="information")
            
            new_repo = user.create_repo(
                name=repo_name,
                private=make_private,
                description=original_description or f"Restored from GitKeeper backup"
            )
            
            # Push from backup to new repo
            git_backup_dir = self.restore_repo_backup_dir / 'git'
            if not git_backup_dir.exists():
                self.notify(f"No git backup found for {repo_name}", severity="error")
                return
            
            # Use temporary directory to push
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_repo_dir = Path(temp_dir) / repo_name
                
                # Clone from backup
                subprocess.run([
                    'git', 'clone', str(git_backup_dir), str(temp_repo_dir)
                ], check=True, capture_output=True)
                
                # Remove existing origin and set new GitHub remote
                subprocess.run([
                    'git', '-C', str(temp_repo_dir), 'remote', 'remove', 'origin'
                ], check=True, capture_output=True)
                
                # Get GitHub token for authenticated URL
                settings = SettingsManager()
                token = settings.get_github_token()
                
                # Add GitHub remote with authentication
                auth_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
                subprocess.run([
                    'git', '-C', str(temp_repo_dir), 'remote', 'add', 'origin', auth_url
                ], check=True, capture_output=True)
                
                # Push all branches and tags
                subprocess.run([
                    'git', '-C', str(temp_repo_dir), 'push', '--all', 'origin'
                ], check=True, capture_output=True)
                
                subprocess.run([
                    'git', '-C', str(temp_repo_dir), 'push', '--tags', 'origin'
                ], check=True, capture_output=True)
            
            self.notify(f"✅ Successfully restored {repo_name} as {privacy_text} repository!", severity="information")
            
        except subprocess.CalledProcessError as e:
            self.notify(f"Git error restoring {repo_name}: {e.stderr.decode()}", severity="error")
        except Exception as e:
            self.notify(f"Error restoring {repo_name}: {str(e)}", severity="error")
    
    def action_back(self) -> None:
        """Return to main dashboard."""
        self.app.pop_screen()


class GitKeeperApp(App):
    """GitKeeper - Main TUI application for GitHub repository management."""
    
    CSS = """
    .title {
        text-align: center;
        text-style: bold;
        color: magenta;
        margin: 1;
    }
    
    .subtitle {
        text-align: center;
        color: white 70%;
        margin-bottom: 2;
    }
    
    .section_title {
        text-style: bold;
        color: cyan;
        margin: 1 0;
    }
    
    .setup_container {
        align: center middle;
        width: 60;
        height: 25;
    }
    
    .setup_form {
        border: solid cyan;
        padding: 2;
        margin: 1;
    }
    
    .buttons {
        align: center middle;
        margin-top: 2;
    }
    
    .repo_buttons {
        height: 3;
        margin: 1 0;
        dock: bottom;
    }
    
    #repos_table {
        height: 1fr;
        max-height: 80%;
    }
    
    .dashboard {
        layout: vertical;
        height: 100%;
    }
    
    .left_panel {
        width: 1fr;
        margin: 1;
        border: solid white 30%;
        padding: 1;
    }
    
    .right_panel {
        width: 2fr;
        margin: 1;
        border: solid white 30%;
        padding: 1;
    }
    
    .info_panel {
        border: solid white 20%;
        padding: 1;
        margin: 1 0;
        min-height: 8;
    }
    
    .action_buttons {
        layout: vertical;
    }
    
    .action_buttons Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    
    .repo_buttons {
        margin-top: 1;
    }
    
    .status_bar {
        dock: bottom;
        height: 1;
        background: blue 20%;
        padding: 0 1;
    }
    
    .progress_container {
        border: solid cyan;
        padding: 1;
        margin: 1;
    }
    
    .log_container {
        border: solid white 30%;
        padding: 1;
        margin: 1;
        height: 15;
    }
    
    .settings_form {
        padding: 1;
        margin: 1;
    }
    
    .settings_form Label {
        margin: 1 0 0 0;
    }
    
    .settings_form Input, .settings_form Select {
        margin: 0 0 1 0;
    }
    """
    
    SCREENS = {
        "setup": SetupScreen,
        "main": MainDashboard,
        "settings": SettingsScreen,
    }
    
    def on_mount(self) -> None:
        """Check if setup is needed on app start."""
        settings = SettingsManager()
        token = settings.get_github_token()
        
        if not token:
            self.push_screen("setup")
        else:
            self.push_screen("main")


if __name__ == "__main__":
    app = GitKeeperApp()
    app.run()
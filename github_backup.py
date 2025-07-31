#!/usr/bin/env python3
"""
GitHub Account Backup Tool
Comprehensive backup of GitHub accounts including repositories, metadata, and settings.
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

import click
from github import Github, GithubException
from git import Repo, GitCommandError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
import requests

from settings import SettingsManager

console = Console()

class GitHubBackup:
    """Main backup class for GitHub accounts."""
    
    def __init__(self, token: str = None, backup_dir: str = None, settings_manager: SettingsManager = None):
        self.settings = settings_manager or SettingsManager()
        
        # Use provided values or fall back to settings
        self.token = token or self.settings.get_github_token()
        self.backup_dir = Path(backup_dir or self.settings.get_backup_directory())
        
        if not self.token:
            raise ValueError("GitHub token not provided and not found in settings")
            
        self.github = Github(self.token)
        self.user = self.github.get_user()
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging - create a new log file for each backup session
        log_file = self.backup_dir / 'backup.log'
        
        # Clear any existing handlers to avoid duplicates
        logging.getLogger().handlers.clear()
        
        # Setup fresh logging for this backup session
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, mode='w'),  # 'w' mode overwrites the file
                logging.StreamHandler()
            ],
            force=True  # Force reconfiguration
        )
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("="*60)
        self.logger.info("Starting GitHub backup session")
        self.logger.info(f"User: {self.user.login}")
        self.logger.info(f"Backup directory: {self.backup_dir}")
        self.logger.info("="*60)
        
    def create_backup_structure(self):
        """Create the backup directory structure."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_root = self.backup_dir / f"github_backup_{self.user.login}_{timestamp}"
        
        directories = [
            'repositories',
            'metadata',
            'issues_prs',
            'wikis',
            'releases',
            'gists',
            'settings'
        ]
        
        for dir_name in directories:
            (self.backup_root / dir_name).mkdir(parents=True, exist_ok=True)
            
        self.logger.info(f"Created backup structure at {self.backup_root}")
        
    def backup_user_metadata(self):
        """Backup user profile and account metadata."""
        console.print("[bold blue]Backing up user metadata...[/bold blue]")
        self.logger.info("Starting user metadata backup")
        
        user_data = {
            'login': self.user.login,
            'name': self.user.name,
            'email': self.user.email,
            'bio': self.user.bio,
            'blog': self.user.blog,
            'location': self.user.location,
            'company': self.user.company,
            'avatar_url': self.user.avatar_url,
            'created_at': self.user.created_at.isoformat() if self.user.created_at else None,
            'updated_at': self.user.updated_at.isoformat() if self.user.updated_at else None,
            'public_repos': self.user.public_repos,
            'private_repos': self.user.total_private_repos,
            'followers': self.user.followers,
            'following': self.user.following,
        }
        
        profile_file = self.backup_root / 'metadata' / 'user_profile.json'
        with open(profile_file, 'w') as f:
            json.dump(user_data, f, indent=2)
        self.logger.info(f"Saved user profile to {profile_file}")
            
        # Backup SSH keys
        try:
            keys = self.user.get_keys()
            ssh_keys = [{'id': key.id, 'key': key.key, 'title': key.title} for key in keys]
            with open(self.backup_root / 'settings' / 'ssh_keys.json', 'w') as f:
                json.dump(ssh_keys, f, indent=2)
        except GithubException as e:
            self.logger.warning(f"Could not backup SSH keys: {e}")
            
    def get_all_repositories(self) -> List:
        """Get all repositories (public and private) for the user."""
        repos = []
        
        # Get owned repositories
        for repo in self.user.get_repos(type='all'):
            repos.append(repo)
            
        return repos
        
    def clone_repository(self, repo, repo_dir: Path):
        """Clone a repository with all branches and history."""
        try:
            clone_url = f"https://{self.token}@github.com/{repo.full_name}.git"
            
            self.logger.info(f"Cloning {repo.full_name} to {repo_dir}")
            self.logger.info(f"Repository details: private={repo.private}, size={repo.size}KB")
            
            # Clone with all branches
            local_repo = Repo.clone_from(
                clone_url, 
                repo_dir,
                multi_options=['--mirror']  # Mirror clone gets all refs
            )
            
            self.logger.info(f"Successfully cloned {repo.full_name}")
            return True
            
        except GitCommandError as e:
            self.logger.error(f"Git command failed for {repo.full_name}: {str(e)}")
            self.logger.error(f"Command output: {e.stderr if hasattr(e, 'stderr') else 'No stderr available'}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error cloning {repo.full_name}: {type(e).__name__}: {str(e)}")
            return False
            
    def backup_repository_metadata(self, repo, repo_dir: Path):
        """Backup repository metadata (issues, PRs, releases, etc.)."""
        metadata = {
            'name': repo.name,
            'full_name': repo.full_name,
            'description': repo.description,
            'private': repo.private,
            'fork': repo.fork,
            'created_at': repo.created_at.isoformat() if repo.created_at else None,
            'updated_at': repo.updated_at.isoformat() if repo.updated_at else None,
            'pushed_at': repo.pushed_at.isoformat() if repo.pushed_at else None,
            'clone_url': repo.clone_url,
            'ssh_url': repo.ssh_url,
            'homepage': repo.homepage,
            'language': repo.language,
            'topics': repo.get_topics(),
            'default_branch': repo.default_branch,
            'archived': repo.archived,
            'disabled': repo.disabled,
        }
        
        # Save basic metadata
        with open(repo_dir / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
            
        # Backup issues
        try:
            issues = []
            for issue in repo.get_issues(state='all'):
                issue_data = {
                    'number': issue.number,
                    'title': issue.title,
                    'body': issue.body,
                    'state': issue.state,
                    'created_at': issue.created_at.isoformat() if issue.created_at else None,
                    'updated_at': issue.updated_at.isoformat() if issue.updated_at else None,
                    'closed_at': issue.closed_at.isoformat() if issue.closed_at else None,
                    'user': issue.user.login if issue.user else None,
                    'labels': [label.name for label in issue.labels],
                    'comments': [
                        {
                            'user': comment.user.login if comment.user else None,
                            'body': comment.body,
                            'created_at': comment.created_at.isoformat() if comment.created_at else None
                        }
                        for comment in issue.get_comments()
                    ]
                }
                issues.append(issue_data)
                
            with open(repo_dir / 'issues.json', 'w') as f:
                json.dump(issues, f, indent=2)
                
        except GithubException as e:
            self.logger.warning(f"Could not backup issues for {repo.full_name}: {e}")
            
        # Backup releases
        try:
            releases = []
            for release in repo.get_releases():
                release_data = {
                    'tag_name': release.tag_name,
                    'name': release.title,
                    'body': release.body,
                    'draft': release.draft,
                    'prerelease': release.prerelease,
                    'created_at': release.created_at.isoformat() if release.created_at else None,
                    'published_at': release.published_at.isoformat() if release.published_at else None,
                    'assets': [
                        {
                            'name': asset.name,
                            'download_url': asset.browser_download_url,
                            'size': asset.size
                        }
                        for asset in release.get_assets()
                    ]
                }
                releases.append(release_data)
                
            with open(repo_dir / 'releases.json', 'w') as f:
                json.dump(releases, f, indent=2)
                
        except GithubException as e:
            self.logger.warning(f"Could not backup releases for {repo.full_name}: {e}")
            
    def backup_repositories(self):
        """Backup all repositories with metadata."""
        repos = self.get_all_repositories()
        self.logger.info(f"Starting backup of {len(repos)} repositories")
        
        clone_success = 0
        clone_failures = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("Backing up repositories...", total=len(repos))
            
            for repo in repos:
                self.logger.info(f"Processing repository: {repo.full_name}")
                progress.update(task, description=f"Backing up {repo.full_name}")
                
                repo_dir = self.backup_root / 'repositories' / repo.name
                repo_dir.mkdir(exist_ok=True)
                
                # Clone repository
                if self.clone_repository(repo, repo_dir / 'git'):
                    console.print(f"✓ Cloned {repo.full_name}")
                    self.logger.info(f"Successfully cloned {repo.full_name}")
                    clone_success += 1
                else:
                    console.print(f"✗ Failed to clone {repo.full_name}", style="red")
                    self.logger.error(f"Failed to clone {repo.full_name}")
                    clone_failures += 1
                    
                # Backup metadata
                self.logger.info(f"Backing up metadata for {repo.full_name}")
                self.backup_repository_metadata(repo, repo_dir)
                
                progress.advance(task)
        
        self.logger.info(f"Repository backup completed: {clone_success} successful, {clone_failures} failed")
                
    def backup_gists(self):
        """Backup all user gists."""
        console.print("[bold blue]Backing up gists...[/bold blue]")
        
        try:
            gists = []
            for gist in self.user.get_gists():
                gist_data = {
                    'id': gist.id,
                    'description': gist.description,
                    'public': gist.public,
                    'created_at': gist.created_at.isoformat() if gist.created_at else None,
                    'updated_at': gist.updated_at.isoformat() if gist.updated_at else None,
                    'files': {
                        filename: {
                            'content': file.content,
                            'language': file.language,
                            'size': file.size
                        }
                        for filename, file in gist.files.items()
                    }
                }
                gists.append(gist_data)
                
            with open(self.backup_root / 'gists' / 'gists.json', 'w') as f:
                json.dump(gists, f, indent=2)
                
            console.print(f"✓ Backed up {len(gists)} gists")
            
        except GithubException as e:
            self.logger.error(f"Failed to backup gists: {e}")
            
    def run_backup(self):
        """Run the complete backup process."""
        console.print(Panel.fit(
            f"[bold green]GitHub Account Backup[/bold green]\n"
            f"Account: {self.user.login}\n"
            f"Backup Directory: {self.backup_dir}",
            title="Backup Starting"
        ))
        
        try:
            self.create_backup_structure()
            self.backup_user_metadata()
            self.backup_repositories()
            self.backup_gists()
            
            # Create backup summary
            summary = {
                'backup_date': datetime.now().isoformat(),
                'user': self.user.login,
                'backup_location': str(self.backup_root),
                'repositories_count': self.user.public_repos + (self.user.total_private_repos or 0),
                'status': 'completed'
            }
            
            with open(self.backup_root / 'backup_summary.json', 'w') as f:
                json.dump(summary, f, indent=2)
                
            console.print(Panel.fit(
                f"[bold green]Backup Completed Successfully![/bold green]\n"
                f"Location: {self.backup_root}\n"
                f"Repositories: {summary['repositories_count']}\n"
                f"Check backup.log for details",
                title="Backup Complete"
            ))
            
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            console.print(f"[bold red]Backup failed: {e}[/bold red]")
            raise

@click.group()
def cli():
    """GitHub Tools - Comprehensive GitHub account management and security tools."""
    pass

@cli.command()
@click.option('--token', '-t', help='GitHub personal access token (optional if set in settings)')
@click.option('--backup-dir', '-d', help='Backup directory path (optional if set in settings)')
@click.option('--dry-run', is_flag=True, help='Show what would be backed up without doing it')
def backup(token: str, backup_dir: str, dry_run: bool):
    """Backup your GitHub account - repositories, issues, PRs, gists, and metadata."""
    
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No actual backup will be performed[/yellow]")
        # TODO: Implement dry run logic
        return
        
    try:
        backup_tool = GitHubBackup(token, backup_dir)
        backup_tool.run_backup()
        
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        return 1

@cli.group()
def settings():
    """Manage tool settings and configuration."""
    pass

@settings.command()
@click.argument('key')
@click.argument('value')
@click.option('--encrypted', '-e', is_flag=True, help='Encrypt the value (for sensitive data)')
@click.option('--description', '-d', help='Description for the setting')
def set(key: str, value: str, encrypted: bool, description: str):
    """Set a configuration value."""
    settings_mgr = SettingsManager()
    settings_mgr.set(key, value, encrypted=encrypted, description=description)
    
    status = "encrypted" if encrypted else "plain"
    console.print(f"✓ Set {key} = {value} ({status})")

@settings.command()
@click.argument('key')
def get(key: str):
    """Get a configuration value."""
    settings_mgr = SettingsManager()
    value = settings_mgr.get(key)
    
    if value is not None:
        console.print(f"{key} = {value}")
    else:
        console.print(f"[red]Setting '{key}' not found[/red]")

@settings.command()
def list():
    """List all configuration settings."""
    settings_mgr = SettingsManager()
    settings_dict = settings_mgr.list_settings()
    
    if not settings_dict:
        console.print("[yellow]No settings configured[/yellow]")
        return
        
    table = Table(title="Configuration Settings")
    table.add_column("Key", style="cyan")
    table.add_column("Encrypted", style="yellow")
    table.add_column("Description", style="green")
    table.add_column("Updated", style="magenta")
    
    for key, info in settings_dict.items():
        encrypted = "✓" if info['encrypted'] else ""
        table.add_row(key, encrypted, info['description'] or "", info['updated_at'])
        
    console.print(table)

@settings.command()
@click.argument('key')
def delete(key: str):
    """Delete a configuration setting."""
    settings_mgr = SettingsManager()
    if settings_mgr.delete(key):
        console.print(f"✓ Deleted setting '{key}'")
    else:
        console.print(f"[red]Setting '{key}' not found[/red]")

@settings.command()
def setup():
    """Interactive setup wizard for initial configuration."""
    settings_mgr = SettingsManager()
    
    console.print(Panel.fit(
        "[bold blue]GitHub Tools Setup Wizard[/bold blue]\n"
        "This will configure your GitHub token and default settings.",
        title="Setup"
    ))
    
    # GitHub token
    token = click.prompt("GitHub Personal Access Token", hide_input=True)
    settings_mgr.set_github_token(token)
    console.print("✓ GitHub token saved (encrypted)")
    
    # Backup directory
    backup_dir = click.prompt("Default backup directory", default="./backups")
    settings_mgr.set_backup_directory(backup_dir)
    console.print(f"✓ Backup directory set to {backup_dir}")
    
    # Parallel workers
    workers = click.prompt("Number of parallel workers", default=4, type=int)
    settings_mgr.set_parallel_workers(workers)
    console.print(f"✓ Parallel workers set to {workers}")
    
    console.print("\n[bold green]Setup complete![/bold green] You can now run:\n")
    console.print("  [cyan]python github_backup.py backup[/cyan] - Start a backup")
    console.print("  [cyan]python github_backup.py settings list[/cyan] - View all settings")
        
    return 0

if __name__ == '__main__':
    cli()
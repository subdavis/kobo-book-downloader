package cmd

import (
	"context"
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/subdavis/kobo-book-downloader/internal/config"
)

type contextKey string

const storeKey contextKey = "store"

var (
	configPath string
	debugMode  bool
	tableFmt   string
)

var rootCmd = &cobra.Command{
	Use:   "kobodl",
	Short: "Download DRM-free books from your Kobo library",
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		if configPath == "" {
			var err error
			configPath, err = config.DefaultPath()
			if err != nil {
				return fmt.Errorf("cannot determine config path: %w", err)
			}
		}
		store, err := config.Load(configPath)
		if err != nil {
			return err
		}
		cmd.SetContext(context.WithValue(cmd.Context(), storeKey, store))
		return nil
	},
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func init() {
	rootCmd.PersistentFlags().StringVar(&configPath, "config", "", "config file (default: $XDG_CONFIG_HOME/kobodl.json)")
	rootCmd.PersistentFlags().BoolVar(&debugMode, "debug", false, "enable debug output")
	rootCmd.PersistentFlags().StringVar(&tableFmt, "fmt", "simple", "table format: simple, grid, csv, markdown")
}

func storeFromCtx(cmd *cobra.Command) *config.Store {
	return cmd.Context().Value(storeKey).(*config.Store)
}

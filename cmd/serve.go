package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
	"github.com/subdavis/kobo-book-downloader/internal/web"
)

var (
	servePort      int
	serveOutputDir string
)

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "start the web UI",
	RunE: func(cmd *cobra.Command, args []string) error {
		store := storeFromCtx(cmd)
		addr := fmt.Sprintf(":%d", servePort)
		fmt.Printf("kobodl web UI listening on http://localhost%s\n", addr)
		srv := web.New(store, serveOutputDir, debugMode)
		return srv.Run(addr)
	},
}

func init() {
	serveCmd.Flags().IntVarP(&servePort, "port", "p", 5000, "port to listen on")
	serveCmd.Flags().StringVarP(&serveOutputDir, "output-dir", "o", "kobo_downloads", "download directory")
	rootCmd.AddCommand(serveCmd)
}

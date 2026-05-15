package cmd

import (
	"fmt"
	"os"

	"github.com/olekukonko/tablewriter"
	"github.com/spf13/cobra"
	"github.com/subdavis/kobo-book-downloader/internal/actions"
	"github.com/subdavis/kobo-book-downloader/internal/config"
)

var bookCmd = &cobra.Command{
	Use:   "book",
	Short: "list and download books",
}

// book list
var (
	bookListUser string
	bookListAll  bool
)

var bookListCmd = &cobra.Command{
	Use:   "list",
	Short: "list books in your library",
	RunE: func(cmd *cobra.Command, args []string) error {
		store := storeFromCtx(cmd)
		users := store.UserList.Users

		if bookListUser != "" {
			u := store.UserList.Get(bookListUser)
			if u == nil {
				return fmt.Errorf("user %q not found", bookListUser)
			}
			users = []*config.User{u}
		}

		books, err := actions.ListBooks(users, store, bookListAll)
		if err != nil {
			return err
		}

		tw := tablewriter.NewWriter(os.Stdout)
		tw.SetHeader([]string{"Title", "Author", "ID", "Flags"})
		tw.SetBorder(false)
		tw.SetAutoWrapText(false)
		for _, b := range books {
			flags := ""
			if b.Audiobook {
				flags += "[audio]"
			}
			if b.Archived {
				flags += "[archived]"
			}
			tw.Append([]string{b.Title, b.Author, b.RevisionId, flags})
		}
		tw.Render()
		return nil
	},
}

// book get
var (
	bookGetUser      string
	bookGetOutputDir string
	bookGetAll       bool
	bookGetFormat    string
)

var bookGetCmd = &cobra.Command{
	Use:   "get [product-id...]",
	Short: "download one or all books",
	RunE: func(cmd *cobra.Command, args []string) error {
		store := storeFromCtx(cmd)
		users := store.UserList.Users

		if len(users) == 0 {
			return fmt.Errorf("no users found — run: kobodl user add")
		}

		var u *config.User
		if bookGetUser != "" {
			u = store.UserList.Get(bookGetUser)
			if u == nil {
				return fmt.Errorf("user %q not found", bookGetUser)
			}
		} else {
			if len(users) > 1 {
				return fmt.Errorf("multiple users — specify one with --user")
			}
			u = users[0]
		}

		if bookGetAll && len(args) > 0 {
			return fmt.Errorf("cannot use --get-all with specific product IDs")
		}
		if !bookGetAll && len(args) == 0 {
			return fmt.Errorf("provide at least one product ID, or use --get-all")
		}

		progress := func(msg string) { fmt.Fprintln(os.Stderr, msg) }

		if bookGetAll {
			_, err := actions.GetBookOrBooks(u, store, bookGetOutputDir, bookGetFormat, "", progress)
			return err
		}

		for _, id := range args {
			_, err := actions.GetBookOrBooks(u, store, bookGetOutputDir, bookGetFormat, id, progress)
			if err != nil {
				return fmt.Errorf("%s: %w", id, err)
			}
		}
		return nil
	},
}

// book wishlist
var bookWishlistUser string

var bookWishlistCmd = &cobra.Command{
	Use:   "wishlist",
	Short: "list your Kobo wishlist",
	RunE: func(cmd *cobra.Command, args []string) error {
		store := storeFromCtx(cmd)
		users := store.UserList.Users

		if bookWishlistUser != "" {
			u := store.UserList.Get(bookWishlistUser)
			if u == nil {
				return fmt.Errorf("user %q not found", bookWishlistUser)
			}
			users = []*config.User{u}
		}

		books, err := actions.GetWishlist(users, store)
		if err != nil {
			return err
		}

		tw := tablewriter.NewWriter(os.Stdout)
		tw.SetHeader([]string{"Title", "Author", "ID", "Price"})
		tw.SetBorder(false)
		tw.SetAutoWrapText(false)
		for _, b := range books {
			tw.Append([]string{b.Title, b.Author, b.RevisionId, b.Price})
		}
		tw.Render()
		return nil
	},
}

func init() {
	bookListCmd.Flags().StringVarP(&bookListUser, "user", "u", "", "filter to one user (email or user ID)")
	bookListCmd.Flags().BoolVar(&bookListAll, "read", false, "include books marked as read")

	bookGetCmd.Flags().StringVarP(&bookGetUser, "user", "u", "", "user to download for (email or user ID)")
	bookGetCmd.Flags().StringVarP(&bookGetOutputDir, "output-dir", "o", "kobo_downloads", "output directory")
	bookGetCmd.Flags().BoolVarP(&bookGetAll, "get-all", "a", false, "download all books")
	bookGetCmd.Flags().StringVarP(&bookGetFormat, "format-str", "f",
		"{Author} - {Title} {ShortRevisionId}",
		"filename format: {Author}, {Title}, {RevisionId}, {ShortRevisionId}. Use / for subdirs.")

	bookWishlistCmd.Flags().StringVarP(&bookWishlistUser, "user", "u", "", "filter to one user")

	bookCmd.AddCommand(bookListCmd, bookGetCmd, bookWishlistCmd)
	rootCmd.AddCommand(bookCmd)
}
